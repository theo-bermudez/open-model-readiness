#!/usr/bin/env python3
"""Build a dependency-free static release from maintained text and checked results.

Only explicit outputs are written. No raw runs, evidence mirrors or environment files
are copied into the deployment root. --check detects stale generated artifacts.
"""
import argparse
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def inline(s):
    saved = []
    def protect(value):
        saved.append(value)
        return f'\x00{len(saved)-1}\x00'
    s = re.sub(r'`([^`]+)`', lambda m: protect('<code>'+html.escape(m[1])+'</code>'), s)
    s = html.escape(s)
    s = re.sub(r'\[([^\]]+)\]\(([^\s)]+)\)', lambda m: '<a href="'+m[2]+'">'+m[1]+'</a>', s)
    s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
    return re.sub(r'\x00(\d+)\x00', lambda m:saved[int(m[1])], s)


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def markdown(text):
    """Render the deliberately small Markdown subset used by our owned templates."""
    lines = text.splitlines(); out = []; i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip(): i += 1; continue
        if line.startswith('```'):
            i += 1; code=[]
            while i < len(lines) and not lines[i].startswith('```'): code.append(lines[i]); i += 1
            if i == len(lines): raise ValueError('unclosed code fence')
            out.append('<pre><code>'+html.escape('\n'.join(code))+'</code></pre>'); i += 1; continue
        heading = re.match(r'^(#{1,6}) (.+)', line)
        if heading:
            level=len(heading[1]); out.append(f'<h{level} id="{slug(heading[2])}">{inline(heading[2])}</h{level}>'); i += 1; continue
        if line.startswith('|'):
            rows=[]
            while i < len(lines) and lines[i].startswith('|'):
                cells=[c.strip() for c in lines[i].strip('|').split('|')]
                if not all(re.fullmatch(r'[: -]+',c) for c in cells): rows.append(cells)
                i += 1
            out.append('<div class="table-scroll" tabindex="0" role="region" aria-label="Scrollable evidence table"><table><thead><tr>'+''.join('<th scope="col">'+inline(c)+'</th>' for c in rows[0])+'</tr></thead><tbody>')
            out.extend('<tr>'+''.join('<td>'+inline(c)+'</td>' for c in row)+'</tr>' for row in rows[1:]);out.append('</tbody></table></div>'); continue
        if line.startswith('- ') or re.match(r'^\d+\. ',line):
            ordered=bool(re.match(r'^\d+\. ',line)); tag='ol' if ordered else 'ul';items=[]
            pattern=r'^\d+\. ' if ordered else r'^- '
            while i<len(lines) and re.match(pattern,lines[i]):
                items.append('<li>'+inline(re.sub(pattern,'',lines[i]))+'</li>');i+=1
            out.append('<'+tag+'>'+''.join(items)+'</'+tag+'>');continue
        para=[line];i+=1
        while i<len(lines) and lines[i].strip() and not re.match(r'^(#|\||```|- |\d+\. )',lines[i]): para.append(lines[i]);i+=1
        out.append('<p>'+inline(' '.join(para))+'</p>')
    return '\n'.join(out)


def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |',*['| '+' | '.join(map(str,r))+' |' for r in rows]])


def context(release,data,nemo,probes):
    runs={r['run_id']:r for r in data['historical_runs']}; comp=data['historical_comparison']
    on=runs[comp['on_run']];off=runs[comp['off_run']]
    invalid=next(r for r in runs.values() if r['status']=='invalid_as_off')
    if comp['causal_speedup_supported']: raise ValueError('first release cannot present a causal historical comparison')
    rows=[]
    for name,label,scale in [('input_sequence_length','Client input tokens (median)',1),('usage_prompt_tokens','Server input tokens (median)',1),('time_to_first_token','First token (median, seconds)',1000),('time_to_first_output_token','First answer (median, seconds)',1000),('request_latency','Request latency (median, seconds)',1000)]:
        rows.append([label,*[f"{r['metrics'][name]['median']/scale:,.2f}" for r in [on,off]]])
    rows += [['Profiled requests',on['profiled_requests'],off['profiled_requests']],['Length-limit stops',on['finish_reasons'].get('length',0),off['finish_reasons'].get('length',0)]]
    head=table(['Historical observation — not a causal comparison','ON · direct','OFF · proxy'],rows)
    replay=data['controlled_replay']
    if replay['status']!='complete': raise ValueError('controlled replay must be explicitly complete for release')
    replay_rows=[]
    for mode in ['on','off']:
        x=replay['by_mode'][mode]
        replay_rows.append([mode.upper(),x['requests'],x['exact_answer_passes'],x['reasoning_present'],x['empty_answers'],x['truncated']])
    replay_summary=(f"Run `{replay['run_id']}`: {replay['profiled_requests']} measured requests, {replay['warmup_requests']} separate same-mode warmups and {replay['complete_matched_pairs']} matched pairs. Four original prompts, three repetitions per mode; native streaming API for both modes. Context {replay['settings']['num_ctx']}, output cap {replay['settings']['num_predict']}, temperature {replay['settings']['temperature']} and seed {replay['settings']['seed']}.\n\n"+table(['Mode','Measured requests','Exact answers passed','Reasoning present','Empty answers','Length stops'],replay_rows)+f"\n\nMeasured wall time: {replay['wall_time_s']:.2f} seconds, including setup and warmups; summed measured-request latency: {replay['timed_requests_total_s']:.2f} seconds. The laptop was on AC power and showed substantial swap usage. Cache was retained: each timed request followed an identical same-mode warmup. This establishes behavior on these short fixtures, not a representative speedup or quality score.")
    nemo_summary=(f"NeMo Evaluator 0.3.0 completed {nemo['counts']['passed_normalized_exact_match']} of {nemo['counts']['profiled_requests']} original fixtures with passing normalized exact-match scores and no model errors in run `{nemo['run_id']}`. This was one repeat per fixture through the existing OFF proxy, not a standard benchmark. Wall time was {nemo['wall_time_s']:.2f} seconds; its evaluation loop reported {nemo['evaluator_elapsed_s']:.2f} seconds. A prior scorer-metadata collision failed and remains excluded. The isolated dependency overlay preserved the historical AIPerf environment. Reasoning-token fields were unavailable, and cache/warmup was not controlled for latency comparison.\n\n"+f"[NeMo method, setup and limitations]({release['repository']}/blob/main/reports/nemo-feasibility.md) · [NeMo results]({release['repository']}/blob/main/results/nemo.json)")
    if probes['status']!='complete_original_probe_suite': raise ValueError('original probes must be complete for release')
    probe_scope=(f"The local original reliability suite tested {len(probes['cases'])} cases with {probes['settings']['repeats']} repeats each: {probes['passes']}/{probes['measured_requests']} objective checks passed. These are narrow fixture checks, not a representative reliability estimate.")
    probe_rows=[[x['category'],f"{x['passes']}/{x['repeats']}",f"{x['pass_population_variance']:.2f}",x['empty_answers'],x['length_finishes']] for x in probes['cases']]
    probe_summary=(f"{probe_scope}\n\nRun `{probes['run_id']}` used the native Ollama API with thinking OFF, context {probes['settings']['num_ctx']}, output cap {probes['settings']['num_predict']}, temperature {probes['settings']['temperature']} and seed {probes['settings']['seed']}. Requests ran sequentially; {probes['request_errors']} request errors and {probes['settings']['retry_count']} retries were recorded. Total wall time was {probes['wall_time_s']:.2f} seconds.\n\n"+table(['Original case','Passed / repeats','Observed pass variance','Empty answers','Length stops'],probe_rows)+f"\n\n[Original prompts and expected answers]({release['repository']}/blob/main/probes.jsonl) · [Scoring implementation]({release['repository']}/blob/main/harness/probes.py) · [Probe results and provenance](results/probes.json)")
    return {'REPO':release['repository'],'SITE':release['site'],'CUTOFF':release['evidence_cutoff'],'RELEASE':release['release'],'ARTICLE_LINK':(' · [Substack article]('+release['article_url']+')') if release['article_url'] else '', 'HEADLINE_TABLE':head,'COVERAGE_TABLE':table(['Model','Runtime / precision','Hardware','Coverage'],release['coverage']),'MATCHED_COUNT':str(comp['matching_full_payloads']),'PROFILE_COUNT':str(on['profiled_requests']),'INVALID_EMPTY':str(invalid['empty_answers']),'INVALID_N':str(invalid['profiled_requests']),'REPLAY_SUMMARY':replay_summary,'NEMO_SUMMARY':nemo_summary,'PROBES_SUMMARY':probe_summary,'PROBES_SCOPE':probe_scope}


def fill(template,c):
    result=re.sub(r'\{\{([A-Z_]+)\}\}',lambda m:c[m[1]],template)
    if '{{' in result: raise ValueError('unresolved template')
    return result


def shell(title,body,release,home=False):
    desc='Request semantics, benchmark validity and practical readiness gates for a local open-model workflow.'
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} · Open Model Readiness</title><meta name="description" content="{desc}">
<meta property="og:title" content="{html.escape(title)} · Open Model Readiness"><meta property="og:description" content="{desc}"><meta property="og:type" content="website"><meta property="og:image" content="{release['site']}assets/social.svg">
<link rel="icon" href="assets/icon.svg" type="image/svg+xml"><link rel="stylesheet" href="assets/style.css"></head>
<body><a class="skip" href="#main">Skip to content</a><header><a class="brand" href="./">OMR<span>Open Model Readiness</span></a><nav aria-label="Main navigation"><a href="./#findings">Findings</a><a href="report.html">Full report</a><a href="reproduce.html">Reproduce</a><a href="{release['repository']}">Code ↗</a></nav></header>
<main id="main" class="{'home' if home else 'document'}">{body}</main><footer><p>Independent work by Theo Bermudez. No NVIDIA affiliation or endorsement.</p><p>Evidence cutoff {release['evidence_cutoff']} · <a href="{release['repository']}/tree/{release['release']}">{release['release']}</a> · <a href="results/m4.json">Results & provenance</a></p></footer></body></html>'''


def home(c,r,d):
    article=r['article_url'] or 'article.html'
    return f'''<section class="hero"><p class="eyebrow">FIELD NOTES / OPEN-MODEL ENABLEMENT</p><h1>When a benchmark works,<br>but measures the wrong thing.</h1><p class="lede">A working endpoint is a beginning. This audit checks whether model settings survive the tooling, comparisons use the same requests, and successful responses actually contain answers.</p><div class="actions"><a class="button" href="report.html">Read the findings <span aria-hidden="true">↗</span></a><a href="reproduce.html">Reproduce the checks →</a></div><div class="scope"><span>TESTED</span> Nemotron-3-Nano-4B · Ollama · Apple M2 laptop<br><small>A small independent case study. GPU and hosted coverage remain planned.</small></div></section>
<section class="verdict"><p class="eyebrow">READINESS DECISION</p><h2>Usable for an instrumented local demo.<br>More evidence needed for deployment.</h2><p>Verify the mode and output limit, inspect finish reasons, and require a nonempty final answer. These tests support integration fixes—not a production-readiness claim.</p></section>
<section id="findings"><div class="section-title"><p class="eyebrow">THREE FINDINGS</p><h2>Check the contract before the chart.</h2></div><article class="finding"><div class="number">01</div><div><p class="tag">REQUEST SEMANTICS · WORKAROUND VERIFIED</p><h3>A string became null. Reasoning stayed on.</h3><p>AIPerf 0.13.0 converted <code>"none"</code> during extra-input parsing. The intended OFF run still returned reasoning. A loopback proxy preserves the literal API value.</p><p><strong>Gate:</strong> inspect the serialized request and the returned behavior.</p><a href="report.html#finding-1-the-requested-reasoning-mode-changed">Evidence and workaround →</a></div></article>
<article class="finding"><div class="number">02</div><div><p class="tag">COMPARISON VALIDITY · HISTORICAL RUNS CONFOUNDED</p><h3>Same seed. Same turns. Different complete prompts.</h3><p>Generated assistant history changed later requests. Only {c['MATCHED_COUNT']} of {c['PROFILE_COUNT']} complete profiled payloads matched, despite matching conversation order.</p><p><strong>Gate:</strong> hash the full message array before claiming a fixed-input comparison.</p><a href="report.html#finding-2-identical-seed-different-complete-requests">See the prompt audit →</a></div></article>
<article class="finding"><div class="number">03</div><div><p class="tag">ANSWER USABILITY · OUTPUT BUDGET MATTERS</p><h3>HTTP success can still leave an empty answer.</h3><p>In the invalid OFF run, {c['INVALID_EMPTY']} of {c['INVALID_N']} profiled responses had no final answer. Every response hit its length limit.</p><p><strong>Gate:</strong> distinguish transport success, reasoning output and usable answers.</p><a href="report.html#finding-3-successful-transport-unusable-answer">Inspect the failure →</a></div></article></section>
<section class="flow-section"><p class="eyebrow">WHERE THE MEANING CHANGED</p><h2>Follow the value through the request.</h2><div class="flow" role="img" aria-label="Intended reasoning_effort string none becomes null in AIPerf parsing; Ollama returns reasoning. A local proxy restores the string before forwarding."><div><small>INTENT</small><code>"none"</code><span>Thinking off requested</span></div><b aria-hidden="true">→</b><div class="fault"><small>CLIENT PARSER</small><code>null</code><span>Value changes type</span></div><b aria-hidden="true">→</b><div><small>OBSERVED RESPONSE</small><code>reasoning</code><span>Mode still on</span></div></div><p class="caption">Conceptual request path for the tested versions. The proxy corrects the value after client parsing.</p></section>
<section><p class="eyebrow">EVIDENCE, WITH BOUNDARIES</p><h2>A small matched check of actual behavior.</h2>{markdown(c['REPLAY_SUMMARY'])}<p><a href="report.html#controlled-local-replay">Method and limitations →</a></p></section>
<section><p class="eyebrow">COVERAGE</p><h2>What has actually been tested.</h2>{markdown(c['COVERAGE_TABLE'])}{markdown(c['PROBES_SCOPE'])}<p><a href="report.html#original-reliability-probes">Probe methods and outcomes →</a></p><p>The <a href="{r['repository']}/blob/main/ROADMAP.md">roadmap</a> separates executed work from resource-dependent experiments.</p></section>
<section class="closing"><div><p class="eyebrow">GO DEEPER</p><h2>Useful evidence.<br>Reproducible decisions.</h2><p>Read the investigation, inspect the code, or start with tests that need no model or API key.</p></div><div class="reading"><a href="{article}">Read the case study <span>↗</span></a><a href="report.html">Full technical report <span>→</span></a><a href="reproduce.html">Reproducibility guide <span>→</span></a><a href="{r['repository']}">Source on GitHub <span>↗</span></a></div></section>'''


def outputs():
    r=json.loads((ROOT/'results/release.json').read_text());d=json.loads((ROOT/'results/m4.json').read_text());n=json.loads((ROOT/'results/nemo.json').read_text());p=json.loads((ROOT/'results/probes.json').read_text());c=context(r,d,n,p)
    texts={name:fill((ROOT/f'content/{name}.md').read_text(),c) for name in ['README','report','reproduce','article']}
    out={'README.md':texts['README'],'RUNBOOK.md':texts['reproduce'],'reports/first-release.md':texts['report'].replace('(results/','(../results/'),'articles/benchmarking-the-wrong-mode.md':texts['article']}
    for name,title in [('report','Full report'),('reproduce','Reproduce'),('article','Benchmarking the wrong mode')]:
        out[f'docs/{name}.html']=shell(title,markdown(texts[name]),r)
    out['docs/index.html']=shell('Check the contract before the chart',home(c,r,d),r,True)
    out['articles/benchmarking-the-wrong-mode.html']=markdown(texts['article'])
    out['docs/.nojekyll']=''
    for path in sorted((ROOT/'site/assets').glob('*')):out['docs/assets/'+path.name]=path.read_text()
    for name in ['m4.json','nemo.json','probes.json','release.json']:out['docs/results/'+name]=(ROOT/'results'/name).read_text()
    return out


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--check',action='store_true');a=ap.parse_args();bad=[]
    for path,text in outputs().items():
        p=ROOT/path
        if a.check:
            if not p.exists() or p.read_text()!=text:bad.append(path)
        else:p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
    if bad:raise SystemExit('Stale generated files: '+', '.join(bad))
    print('Public build '+('is current' if a.check else 'complete'))

if __name__=='__main__':main()
