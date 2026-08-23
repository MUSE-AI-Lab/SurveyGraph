
from __future__ import annotations

import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, List, Tuple

import networkx as nx
import requests
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments import offline_real_revision_audit as base

OUT = ROOT / "outputs" / "openalex_citation_core_audit_20260525"
RAW = OUT / "raw_openalex"
OUT.mkdir(parents=True, exist_ok=True)
RAW.mkdir(parents=True, exist_ok=True)

OPENALEX = "https://api.openalex.org/works"
PARAMS_BASE = {
    "per-page": "5",
    "select": "id,doi,display_name,publication_year,cited_by_count",
    "mailto": "noreply@example.com",
}


def norm_title(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def cache_name(title: str) -> str:
    import hashlib
    return hashlib.sha1(title.encode("utf-8", errors="ignore")).hexdigest() + ".json"


def title_similarity(a: str, b: str) -> float:
    na, nb = norm_title(a), norm_title(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def fetch_openalex(title: str) -> Dict[str, Any]:
    cache = RAW / cache_name(title)
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    params = dict(PARAMS_BASE)
    params["search"] = title[:240]
    for attempt in range(3):
        try:
            r = requests.get(OPENALEX, params=params, timeout=30)
            if r.status_code == 429:
                time.sleep(2 + attempt)
                continue
            r.raise_for_status()
            data = r.json()
            cache.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return data
        except Exception as e:
            if attempt == 2:
                data = {"error": f"{type(e).__name__}: {e}", "results": []}
                cache.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                return data
            time.sleep(1 + attempt)
    return {"results": []}


def match_title(title: str, year: Any, data: Dict[str, Any]) -> Dict[str, Any]:
    best = None
    best_score = -1.0
    for item in data.get("results", []) or []:
        sim = title_similarity(title, item.get("display_name", ""))
        y = item.get("publication_year")
        year_penalty = 0.0
        if isinstance(year, int) and isinstance(y, int):
            year_penalty = min(abs(year - y), 5) * 0.015
        score = sim - year_penalty
        if score > best_score:
            best_score = score
            best = item
    if not best:
        return {"matched": False, "match_score": 0.0, "cited_by_count": 0}
    sim = title_similarity(title, best.get("display_name", ""))
    y = best.get("publication_year")
    year_ok = True
    if isinstance(year, int) and isinstance(y, int):
        year_ok = abs(year - y) <= 3
    matched = sim >= 0.86 and year_ok
    return {
        "matched": matched,
        "match_score": sim,
        "openalex_id": best.get("id"),
        "doi": best.get("doi"),
        "openalex_title": best.get("display_name"),
        "openalex_year": y,
        "cited_by_count": int(best.get("cited_by_count") or 0) if matched else 0,
    }


def graph_scores(run: base.RunBundle, citation_map: Dict[str, int] | None = None) -> Dict[str, Any]:
    papers = run.mekg.get("papers", [])
    paper_map = {p["id"]: p for p in papers}
    graph = nx.DiGraph()
    graph.add_nodes_from(paper_map)
    for rel in run.mekg.get("relations", []):
        src, tgt = rel.get("source"), rel.get("target")
        if src in paper_map and tgt in paper_map:
            graph.add_edge(src, tgt)
    pagerank = nx.pagerank(graph, alpha=0.85) if graph.number_of_nodes() else {}
    if pagerank:
        mx, mn = max(pagerank.values()), min(pagerank.values())
        rng = mx - mn if mx != mn else 1.0
        pagerank = {pid: (v - mn) / rng for pid, v in pagerank.items()}
    citations=[]; years=[]; degrees=[]
    for pid in graph.nodes():
        p=paper_map[pid]
        c = citation_map.get(pid, 0) if citation_map is not None else p.get("citations", p.get("citation_count", 0))
        if isinstance(c,(int,float)) and c>=0: citations.append(c)
        y=p.get("year",2024)
        if isinstance(y,int) and 1900<y<=2026: years.append(y)
        degrees.append(graph.in_degree(pid)+graph.out_degree(pid))
    max_c=max(citations) if citations else 1
    min_y=min(years) if years else 2014
    max_y=max(years) if years else 2026
    y_rng=max_y-min_y if max_y>min_y else 1
    max_d=max(degrees) if degrees else 1
    weights={"pagerank":0.4,"citation":0.3,"recency":0.2,"degree":0.1}
    scores={}
    components={}
    for pid in graph.nodes():
        p=paper_map[pid]
        pr=pagerank.get(pid,0.0)
        c = citation_map.get(pid, 0) if citation_map is not None else p.get("citations", p.get("citation_count",0))
        if not isinstance(c,(int,float)) or c<0: c=0
        cscore=math.log1p(c)/math.log1p(max_c) if max_c>0 else 0.0
        y=p.get("year",2024)
        if not isinstance(y,int) or y<1900 or y>2026: y=2024
        rscore=(y-min_y)/y_rng if y_rng>0 else 0.5
        d=graph.in_degree(pid)+graph.out_degree(pid)
        dscore=d/max_d if max_d>0 else 0.0
        scores[pid]=weights["pagerank"]*pr+weights["citation"]*cscore+weights["recency"]*rscore+weights["degree"]*dscore
        components[pid]={"pagerank":pr,"citation_score":cscore,"recency":rscore,"degree":dscore,"citations":c}
    ranked=sorted(scores.items(), key=lambda x:x[1], reverse=True)
    top10=[pid for pid,_ in ranked[:10]]
    return {"top10_ids":top10,"top10_titles":[paper_map[pid].get("title","") for pid in top10],"scores":scores,"components":components}


def main() -> None:
    runs=base.load_archived_runs()
    paper_refs=[]
    seen={}
    for run in runs:
        for p in run.mekg.get("papers",[]):
            title=p.get("title","")
            key=norm_title(title)
            if key and key not in seen:
                seen[key]={"title":title,"year":p.get("year")}
    titles=list(seen.values())
    print(f"Unique titles to query: {len(titles)}")
    matches={}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs={ex.submit(fetch_openalex, item["title"]): item for item in titles}
        for i,fut in enumerate(as_completed(futs),1):
            item=futs[fut]
            data=fut.result()
            matches[norm_title(item["title"])] = match_title(item["title"], item.get("year"), data)
            if i % 100 == 0:
                print(f"matched {i}/{len(titles)}")
    (OUT/"openalex_title_matches.json").write_text(json.dumps(matches,ensure_ascii=False,indent=2),encoding="utf-8")

    per_run=[]
    coverage=[]; nonzero=[]; overlaps=[]; citation_values=[]
    for run in runs:
        citation_map={}
        matched_count=0; nonzero_count=0
        for p in run.mekg.get("papers",[]):
            m=matches.get(norm_title(p.get("title","")),{})
            c=int(m.get("cited_by_count") or 0)
            citation_map[p["id"]]=c
            if m.get("matched"):
                matched_count+=1
            if c>0:
                nonzero_count+=1
                citation_values.append(c)
        zero_score=graph_scores(run, None)
        enriched_score=graph_scores(run, citation_map)
        overlap=len(set(zero_score["top10_ids"]) & set(enriched_score["top10_ids"]))
        coverage.append(matched_count/len(run.mekg.get("papers",[])))
        nonzero.append(nonzero_count/len(run.mekg.get("papers",[])))
        overlaps.append(overlap)
        per_run.append({
            "run_id":run.run_id,
            "label":run.label,
            "paper_count":len(run.mekg.get("papers",[])),
            "matched_openalex_titles":matched_count,
            "openalex_match_rate":matched_count/len(run.mekg.get("papers",[])),
            "nonzero_citation_papers":nonzero_count,
            "nonzero_citation_rate":nonzero_count/len(run.mekg.get("papers",[])),
            "top10_overlap_zero_vs_openalex":overlap,
            "zero_citation_top10_titles":zero_score["top10_titles"],
            "openalex_citation_top10_titles":enriched_score["top10_titles"],
            "openalex_top10_citations":[enriched_score["components"][pid]["citations"] for pid in enriched_score["top10_ids"]],
        })
    result={
        "experiment_type":"openalex_citation_proxy_core_score_audit",
        "scope_note":"External OpenAlex title-match citation proxy over archived MEKG paper records; recomputes the default core-paper score with nonzero citation counts without mutating archived artifacts.",
        "match_threshold":"title similarity >= 0.86 and publication-year difference <= 3 when available",
        "aggregate":{
            "runs":len(runs),
            "unique_titles_queried":len(titles),
            "mean_openalex_match_rate":mean(coverage),
            "median_openalex_match_rate":median(coverage),
            "mean_nonzero_citation_rate":mean(nonzero),
            "median_nonzero_citation_rate":median(nonzero),
            "runs_with_nonzero_citation_signal":sum(1 for v in nonzero if v>0),
            "mean_top10_overlap_zero_vs_openalex":mean(overlaps),
            "median_top10_overlap_zero_vs_openalex":median(overlaps),
            "citation_count_mean_nonzero":mean(citation_values) if citation_values else 0,
            "citation_count_median_nonzero":median(citation_values) if citation_values else 0,
        },
        "per_run":per_run,
    }
    (OUT/"openalex_citation_core_audit.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["# OpenAlex Citation Proxy Core-Score Audit","",f"- Unique titles queried: {len(titles)}",f"- Mean OpenAlex title-match rate: {result['aggregate']['mean_openalex_match_rate']*100:.1f}%",f"- Mean non-zero citation rate: {result['aggregate']['mean_nonzero_citation_rate']*100:.1f}%",f"- Runs with non-zero citation signal: {result['aggregate']['runs_with_nonzero_citation_signal']}/{len(runs)}",f"- Mean top-10 overlap between zero-citation and OpenAlex-enriched scoring: {result['aggregate']['mean_top10_overlap_zero_vs_openalex']:.2f}/10","","| Run | Match | Nonzero cite | Top-10 overlap |","|---|---:|---:|---:|"]
    for r in per_run:
        lines.append(f"| {r['label']} | {r['openalex_match_rate']*100:.1f}% | {r['nonzero_citation_rate']*100:.1f}% | {r['top10_overlap_zero_vs_openalex']}/10 |")
    (OUT/"openalex_citation_core_audit.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps(result["aggregate"],ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
