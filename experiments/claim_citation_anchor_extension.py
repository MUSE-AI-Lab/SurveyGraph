
from __future__ import annotations
import json, re, math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs'/'claim_citation_anchor_extension_20260525'
OUT.mkdir(parents=True, exist_ok=True)
RUNS=[
    ('20251224_204059_d990305f','Document Visual Question Answering'),
    ('20251224_191320_a9e4ed89','Text-to-SQL Agent'),
    ('2025-12-23-1426_Large_Language_Model','Large Language Model Function Calling'),
]
STOP=set('the a an and or of to in on for with by from via using based this that these those is are was were be been as at into between among over under through than then such can may might should would could our their its it we they paper papers method methods model models system systems task tasks approach approaches results work works study studies survey'.split())

def clean_tex(s:str)->str:
    s=re.sub(r'%.*',' ',s)
    s=re.sub(r'\\(section|subsection|subsubsection)\*?\{[^{}]*\}','. ',s)
    s=re.sub(r'\\[a-zA-Z]+\*?(\[[^\]]*\])?',' ',s)
    s=re.sub(r'[{}$]',' ',s)
    return re.sub(r'\s+',' ',s).strip()

def tokens(s:str)->set[str]:
    toks=re.findall(r'[A-Za-z][A-Za-z0-9\-]{2,}', clean_tex(s).lower())
    return {t for t in toks if t not in STOP and len(t)>3}

def split_sentences(tex:str)->List[str]:
    # Keep cite commands during splitting.
    tex=re.sub(r'(?m)^%.*$',' ',tex)
    chunks=re.split(r'(?<=[.!?])\s+(?=[A-Z\\])', tex)
    out=[]
    for c in chunks:
        if '\\cite' in c and len(c)<1000:
            out.append(c.strip())
    return out

def cite_keys(sentence:str)->List[str]:
    keys=[]
    for m in re.finditer(r'\\cite[a-zA-Z]*\{([^{}]+)\}', sentence):
        for k in m.group(1).split(','):
            k=k.strip()
            if k: keys.append(k)
    return keys

def load_paper(run_dir:Path,key:str)->Dict[str,Any]|None:
    p=run_dir/'papers'/f'{key}.json'
    if p.exists():
        try: return json.loads(p.read_text(encoding='utf-8'))
        except Exception: return None
    return None

def main():
    rows=[]
    for run_id,topic in RUNS:
        run_dir=ROOT/'outputs'/run_id
        tex_path=run_dir/'latex'/'survey.tex'
        if not tex_path.exists(): continue
        tex=tex_path.read_text(encoding='utf-8',errors='ignore')
        candidates=[]
        for sent in split_sentences(tex):
            keys=cite_keys(sent)
            if len(keys)!=1: continue
            paper=load_paper(run_dir,keys[0])
            if not paper: continue
            claim_toks=tokens(sent)
            evidence=f"{paper.get('title','')} {paper.get('abstract','')} {paper.get('md_text','')[:20000]}"
            ev_toks=tokens(evidence)
            if not claim_toks or not ev_toks: continue
            overlap=claim_toks & ev_toks
            precision=len(overlap)/len(claim_toks)
            recall=len(overlap)/len(ev_toks) if ev_toks else 0
            jaccard=len(overlap)/len(claim_toks|ev_toks)
            # Conservative lexical anchoring categories, not semantic entailment.
            if len(overlap)>=5 and precision>=0.18:
                label='anchored'
            elif len(overlap)>=3 and precision>=0.10:
                label='partial_anchor'
            else:
                label='weak_or_missing_anchor'
            candidates.append({
                'topic':topic,'run_id':run_id,'citation_key':keys[0],
                'sentence':clean_tex(sent),'paper_title':paper.get('title',''),
                'overlap_terms':sorted(list(overlap))[:20],
                'claim_token_count':len(claim_toks),'evidence_token_count':len(ev_toks),
                'overlap_count':len(overlap),'overlap_precision':precision,'overlap_recall':recall,'overlap_jaccard':jaccard,'label':label,
            })
        # deterministic diverse sample: sort by citation key+sentence and take 24 per topic
        candidates=sorted(candidates, key=lambda r:(r['citation_key'], r['sentence']))[:24]
        rows.extend(candidates)
    counts=Counter(r['label'] for r in rows)
    by_topic=defaultdict(Counter)
    for r in rows: by_topic[r['topic']][r['label']]+=1
    total=len(rows)
    anchored=counts['anchored']; partial=counts['partial_anchor']; weak=counts['weak_or_missing_anchor']
    result={
        'experiment_type':'generated_claim_citation_lexical_anchor_extension',
        'scope_note':'Deterministic zero-API extension over sampled single-citation generated-survey sentences. Labels measure lexical anchoring against repository-local cited title/abstract text, not full semantic entailment or human citation-support precision.',
        'topic_count':len(RUNS),'sample_count':total,
        'overall':{
            'anchored':anchored,'partial_anchor':partial,'weak_or_missing_anchor':weak,'total':total,
            'anchored_or_partial_rate':(anchored+partial)/total if total else 0,
            'anchored_rate':anchored/total if total else 0,
        },
        'by_topic':{topic:dict(cnt) for topic,cnt in by_topic.items()},
        'samples':rows,
    }
    (OUT/'claim_citation_lexical_anchor_extension.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# Claim-to-Citation Lexical Anchor Extension','',f"- Samples: {total} single-citation sentences across {len(RUNS)} topics",f"- Anchored: {anchored}/{total} ({(anchored/total*100 if total else 0):.1f}%)",f"- Anchored-or-partial: {anchored+partial}/{total} ({((anchored+partial)/total*100 if total else 0):.1f}%)",'', '| Topic | Anchored | Partial | Weak/missing |','|---|---:|---:|---:|']
    for topic,cnt in by_topic.items():
        lines.append(f"| {topic} | {cnt.get('anchored',0)} | {cnt.get('partial_anchor',0)} | {cnt.get('weak_or_missing_anchor',0)} |")
    lines.append('')
    lines.append('> This is a lexical anchoring audit, not a substitute for blinded human entailment annotation.')
    (OUT/'claim_citation_lexical_anchor_extension.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(result['overall'],ensure_ascii=False,indent=2))

if __name__=='__main__': main()
