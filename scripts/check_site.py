#!/usr/bin/env python3
"""Check static HTML links/assets/fragments and public deployment boundaries."""
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote,urlsplit

ROOT=Path(__file__).resolve().parents[1]
class Page(HTMLParser):
    def __init__(self,text):
        super().__init__();self.links=[];self.ids=set();self.h1=0;self.title=False;self.feed(text)
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.add(a['id'])
        if tag=='h1':self.h1+=1
        if tag=='title':self.title=True
        for k in ['href','src']:
            if k in a:self.links.append(a[k])

def main():
    root=ROOT/'docs';pages={p:Page(p.read_text()) for p in root.rglob('*.html')};errors=[];external=set()
    for p,page in pages.items():
        if page.h1!=1 or not page.title:errors.append(f'{p.name}: missing title or not exactly one h1')
        for link in page.links:
            u=urlsplit(link)
            if u.scheme in ['http','https']:external.add(link);continue
            if u.scheme:errors.append(f'{p.name}: unexpected link scheme {u.scheme}');continue
            if u.path.startswith('/'):errors.append(f'{p.name}: absolute path breaks project Pages: {link}');continue
            dest=(p.parent/unquote(u.path)).resolve() if u.path else p
            if dest.is_dir():dest/= 'index.html'
            if not dest.is_relative_to(root.resolve()):errors.append(f'{p.name}: escapes site: {link}');continue
            if not dest.is_file():errors.append(f'{p.name}: missing target: {link}');continue
            if u.fragment and dest in pages and unquote(u.fragment) not in pages[dest].ids:errors.append(f'{p.name}: missing fragment: {link}')
    allowed={'.html','.css','.svg','.json'}
    for p in root.rglob('*'):
        if p.is_file() and p.name!='.nojekyll' and p.suffix not in allowed:errors.append(f'unreviewed deployment type: {p.relative_to(root)}')
        if p.is_file() and p.stat().st_size>2_000_000:errors.append(f'oversized deployment file: {p.name}')
    if errors:raise SystemExit('\n'.join(errors))
    print(f'Checked {len(pages)} pages: all local links, assets and fragments resolve; deployment boundary clean')
    print('External links requiring live verification:')
    print('\n'.join(sorted(external)))
if __name__=='__main__':main()
