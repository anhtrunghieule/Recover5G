#!/usr/bin/env python3
"""Recover5G artifact: regenerate the paper's numbers from the included data and compare them with the paper.

  python3 check_values.py               quick check: run the macro generators on the included summaries (about 1 min)
  python3 check_values.py --from-raw    also rerun the offline evaluators and analyses on the per-run records first
                                        (about 10 to 20 min, most of it decoding text captures for the organic chains)
Options:
  --out DIR       output folder (default: out/ beside this script; it is replaced on each run)
  --keep-work     keep the working copy of the data under DIR/work (deleted by default)

Nothing outside --out is written. The included data and code are copied to DIR/work first, every step runs on that
copy, and the generators write their macro files to DIR/generated/. Docker, pmset, colima and tshark are replaced by
stubs that fail, so no step can reach a container runtime or the host power log. Python 3.9+ standard library only.

Result: DIR/quickcheck_report.json (one entry per paper value) and DIR/quickcheck_summary.txt. Exit status 0 when every
regenerable value matches expected/paper_values.json, 1 otherwise.
"""
import argparse, csv, json, os, re, shutil, subprocess, sys, tempfile, time

ART = os.path.dirname(os.path.abspath(__file__))
WS_SRC = os.path.join(ART, "workspace")
HIST_SRC = os.path.join(ART, "reproduction", "evidence", "archive-20261126", "historical-artifact")
VERDICT_SRC = os.path.join(ART, "reproduction", "testbed", "r5g", "verdict.py")
EXPECTED = os.path.join(ART, "expected", "paper_values.json")

# Macro files in the order main.tex reads them (a later definition overrides an earlier one), mapped to the folder
# under DIR/generated that holds the regenerated file. None: no generator in the artifact.
ORDER = [("generated/macros.tex", "historical"), ("generated-rerun/macros_rerun.tex", None),
         ("generated-rerun/macros_extra.tex", None), ("generated-rev25/macros_rev25.tex", "rev25"),
         ("generated-rev26/macros_rev26.tex", "rev26"), ("generated-rev27/macros_rev27.tex", "rev27"),
         ("generated-rev28/macros_rev28.tex", "rev28"), ("generated-rev28/macros_rev28b.tex", "rev28b"),
         ("generated-rev28/macros_pending.tex", None), ("generated-validation/macros_validation.tex", None),
         ("generated-rev29/macros_rev29.tex", "rev29"), ("generated-f5g/macros_f5g.tex", "f5g"),
         ("generated-audit/corrections.tex", "corrections")]
NOT_REGENERABLE = {
    "generated-rerun/macros_rerun.tex": "earlier rerun campaign (10 to 19 Nov 2026, synced from repository commit 9c9d721); "
                                        "its raw records and its generator rerun/render.py are not in this artifact",
    "generated-rerun/macros_extra.tex": "earlier rerun campaign (10 to 19 Nov 2026, synced from repository commit 9c9d721); "
                                        "its raw records and its generator rerun/paper_macros.py are not in this artifact",
    "generated-validation/macros_validation.tex": "fresh-validation cohort; regenerate with reproduction/render_validation.py",
}
AI_READER = "ai-reader experiment folder is not distributed with this artifact (machine-reader decisions)"
FIG = {"fig_scale_data.tex": "rev28b", "fig_exhaust_data.tex": "rev26"}
TABLES = {"generated-rev28/tab_organic_chains.tex": "rev28b", "generated-rev28/tab_scale_chains.tex": "rev28b",
          "generated-rev28/tab_scale_udm_chains.tex": "rev28b",
          "generated/tab_delta.tex": "historical", "generated/tab_reduction.tex": "historical",
          "generated/tab_taxonomy.tex": "historical", "generated/tab_validity.tex": "historical"}
ACC_SRC = os.path.join(ART, "reproduction", "evidence", "archive-20261126", "accumulation")
REJECT_ARMS = [("none", "None"), ("targeted", "PCF/UDM"), ("global", "All NFs")]

# Offline evaluators and analyses for --from-raw, in dependency order: (name, cwd relative to the workspace, argv, env).
def raw_steps(W):
    R = os.path.join(W, "results", "raw")
    s = [("orphan_eval", "testbed", ["exp/orphan_eval.py", R + "/orphan", R + "/orphan-oai"], {}),
         ("orphan_wire_truth", "testbed", ["exp/wire_truth.py", R + "/orphan", "--kind", "orphan"], {}),
         ("orphan_ref_eval", "testbed", ["exp/orphan_ref_eval.py", R + "/orphan"], {}),
         ("orphan_rebuild_eval", "testbed", ["exp/orphan_eval.py", R + "/orphan-rebuild"], {}),
         ("crossue_eval", "testbed", ["exp/crossue_eval.py", R + "/crossue"], {}),
         ("heldout_wire_truth", "testbed", ["exp/wire_truth.py", R + "/heldout", "--kind", "heldout"], {}),
         ("heldout_eval", "testbed", ["exp/heldout_eval.py", R + "/heldout"], {}),
         ("timing_eval", "testbed", ["exp/timing_eval.py", R + "/timing"], {})]
    for c in ("g0", "g10", "g150", "v150"):
        s += [("timing_wire_truth_" + c, "testbed", ["exp/wire_truth.py", R + "/timing", "--kind", "heldout", "--src",
               "timing_%s.jsonl" % c, "--dst", "wire_truth_timing_%s.jsonl" % c, "--default-offset", "0.1"], {}),
              ("timing_ref_" + c, "testbed", ["exp/heldout_eval.py", R + "/timing", "timing_%s.jsonl" % c,
               "wire_truth_timing_%s.jsonl" % c, "timingref_" + c], {})]
    s += [("f5g_eval", "testbed", ["exp/f5g_eval.py", R + "/free5gc"], {}),
          ("main_eval", "testbed", ["exp/main_eval.py", R + "/main"], {}),
          ("idref_main", "testbed", ["exp/idref_eval.py", R + "/main", "--out", R + "/idref", "--no-decode", "--tag", "main"], {}),
          ("main_yield", "testbed", ["exp/main_yield.py", R + "/main", R + "/idref/main"], {}),
          ("impact_eval", "testbed", ["exp/impact_eval.py"], {"R5G_OUT": R + "/impact"}),
          ("timing2_eval", "testbed", ["exp/timing2_eval.py", R + "/timing2"], {}),
          ("upfix_eval", "testbed", ["exp/upfix_eval.py", R + "/upfix"], {}),
          ("upfix_orphan_eval", "testbed", ["exp/orphan_eval.py", R + "/upfix/orphan"], {}),
          ("organic_eval", "testbed", ["exp/organic_eval.py"], {}),
          ("scale_eval", "testbed", ["exp/scale_eval.py"], {}),
          ("scale_pcap_seid", "testbed", ["exp/scale_pcap_seid.py", "--out", R + "/scale/pcap_seid_summary.json"], {}),
          ("killtime_eval", "testbed", ["exp/killtime_eval.py"], {}),
          ("clean3_eval", ".", ["analysis-r1/scripts/clean3_eval.py"], {}),
          ("a1_build_runs", ".", ["analysis-r1/scripts/build_runs.py"], {}),
          ("a1_item1_checkers", ".", ["analysis-r1/scripts/item1_checkers.py"], {}),
          ("a1_item2_reference", ".", ["analysis-r1/scripts/item2_reference.py"], {}),
          ("a1_item345", ".", ["analysis-r1/scripts/item345.py"], {}),
          ("a1_item6_bookkeeping", ".", ["analysis-r1/scripts/item6_bookkeeping.py"], {})]
    for n in ("item1_gap", "item1_delaystate", "item1_rereg", "item23", "item45_parse", "item45_bound", "item45_cases",
              "item45_status", "item45_summary", "item7_counts", "item7_persist_def", "item8_provenance"):
        s.append(("a3_" + n, ".", ["analysis-r3/scripts/%s.py" % n], {}))
    # paper/cost.py is not rerun: it sums wall time over every results/raw/*/*.jsonl and was run on 25 November 2026,
    # before the later cohorts added record formats it does not parse. results/cost.json is kept as computed then.
    s += [("model_macros", ".", ["paper/model_macros.py", W], {})]
    return s


def braced(t, i):
    d, j = 0, i
    while True:
        c = t[j]
        if c == "\\":
            j += 2; continue
        if c == "{":
            d += 1
        elif c == "}":
            d -= 1
            if d == 0:
                return t[i + 1:j], j + 1
        j += 1


def parse_rx(path):
    t = open(path).read()
    return {m.group(1): braced(t, m.end())[0] for m in re.finditer(r"\\expandafter\\def\\csname rx@(.*?)\\endcsname", t)}


def parse_named(path):
    t = open(path).read()
    out = {}
    for m in re.finditer(r"\\newcommand\{\\([A-Za-z]+)\}\{", t):
        out[m.group(1)] = braced(t, m.end() - 1)[0]
    return out


def parse_defs(path):
    t = open(path).read()
    return {m.group(1): braced(t, m.end() - 1)[0] for m in re.finditer(r"\\def\\([A-Za-z]+)\{", t)}


def body(path):
    return "\n".join(l for l in open(path).read().splitlines() if not l.startswith("%") and "\\caption" not in l)


class Runner:
    def __init__(self, out, log):
        self.out, self.log, self.steps = out, log, []
        self.fake = os.path.join(out, "work", "offline-bin")
        os.makedirs(self.fake, exist_ok=True)
        for b in ("docker", "pmset", "colima", "tshark", "caffeinate"):
            p = os.path.join(self.fake, b)
            open(p, "w").write('#!/bin/sh\necho "check_values.py: %s is disabled in the offline check" >&2\nexit 97\n' % b)
            os.chmod(p, 0o755)

    def run(self, name, argv, cwd, extra_env=None, timeout=3600):
        env = dict(os.environ, PATH=self.fake + os.pathsep + os.environ.get("PATH", ""), PYTHONDONTWRITEBYTECODE="1",
                   DOCKER_CONTEXT="offline-check-no-docker", IDREF_DOCKER_CONTEXT="offline-check-no-docker")
        env.update(extra_env or {})
        lp = os.path.join(self.log, name + ".log")
        t0 = time.monotonic()
        with open(lp, "w") as fh:
            try:
                rc = subprocess.run([sys.executable, "-B"] + argv, cwd=cwd, env=env, stdout=fh, stderr=subprocess.STDOUT,
                                    timeout=timeout).returncode
            except subprocess.TimeoutExpired:
                rc = "timeout"
        dt = round(time.monotonic() - t0, 1)
        self.steps.append({"step": name, "returncode": rc, "seconds": dt, "log": os.path.relpath(lp, self.out)})
        print("  %-28s %s  %6.1fs" % (name, "ok" if rc == 0 else "FAILED (%s)" % rc, dt), flush=True)
        return rc == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-raw", action="store_true")
    ap.add_argument("--out", default=os.path.join(ART, "out"))
    ap.add_argument("--keep-work", action="store_true")
    a = ap.parse_args()
    out = os.path.abspath(a.out)
    if out == ART or (os.path.commonpath([out, ART]) == ART and
                      os.path.relpath(out, ART).split(os.sep)[0] in ("workspace", "reproduction", "expected", "environment", "tools")):
        sys.exit("--out must be a new folder or out/, not a folder of the artifact itself")
    if os.path.exists(out):
        if os.listdir(out) and not os.path.exists(os.path.join(out, "quickcheck_summary.txt")) and \
           not os.path.isdir(os.path.join(out, "work")):
            sys.exit("--out %s exists and does not hold an earlier check; choose a new folder" % out)
        shutil.rmtree(out)
    work, gen, logs = os.path.join(out, "work"), os.path.join(out, "generated"), os.path.join(out, "logs")
    for d in (work, gen, logs):
        os.makedirs(d)
    r = Runner(out, logs)
    t_start = time.monotonic()

    print("Copying the workspace to %s" % work, flush=True)
    heavy = shutil.ignore_patterns("pcap", "decode", "events", "logs", "job-logs", "build-logs", "*.pcap.gz", "*.idref.jsonl",
                                   "__pycache__")
    W = os.path.join(work, "workspace")
    shutil.copytree(WS_SRC, W, ignore=None if a.from_raw else heavy, symlinks=True)
    # item8_provenance.py and analysis-r1/scripts/a1_lib.py read the fresh-validation evidence beside the workspace.
    os.symlink(os.path.join(ART, "reproduction"), os.path.join(work, "reproduction"))

    if a.from_raw:
        print("Rerunning the offline evaluators and analyses on the per-run records", flush=True)
        for name, cwd, argv, env in raw_steps(W):
            r.run(name, argv, os.path.join(W, cwd), env)

    print("Running the macro generators", flush=True)
    P = os.path.join(W, "paper")
    r.run("gen_rev25", [P + "/gen_macros.py", W, gen + "/rev25"], W)
    r.run("gen_rev26", [P + "/gen_macros_rev26.py", W, gen + "/rev26"], W)
    r.run("gen_rev27", [P + "/gen_macros_rev27.py", W, gen + "/rev27"], W)
    if r.run("gen_rev28", [P + "/gen_macros_rev28.py", W], W):      # rev28b and rev29 read its csv in the workspace
        shutil.copytree(os.path.join(W, "analysis-r1", "generated-rev28"), gen + "/rev28")
    r.run("gen_rev28b", [P + "/gen_macros_rev28b.py", W, gen + "/rev28b"], W)
    if r.run("gen_rev29", [P + "/gen_macros_rev29.py", W], W):
        shutil.copytree(os.path.join(W, "analysis-r3", "generated-rev29"), gen + "/rev29")
    if r.run("gen_f5g", [P + "/gen_macros_f5g.py"], W):
        shutil.copytree(os.path.join(W, "analysis-r3", "f5g", "generated"), gen + "/f5g")

    # generated-audit/corrections.tex: the held-out evaluator with the stricter convergence rule of the earlier
    # package (r5g/verdict.py first_stably_clean), then the rev25 generator; corrections = keys that change.
    print("Recomputing the convergence correction", flush=True)
    ok = False
    try:
        cw = os.path.join(work, "corrections", "workspace")
        shutil.copytree(W, cw, ignore=shutil.ignore_patterns("pcap", "decode", "events", "*.pcap.gz", "*.idref.jsonl"), symlinks=True)
        shutil.copy(VERDICT_SRC, os.path.join(cw, "testbed", "r5g", "verdict.py"))
        ev = os.path.join(cw, "testbed", "exp", "heldout_eval.py")
        t = open(ev).read()
        old = ('"first_ref_clean_t": next((r["rel"] for i, r in enumerate(rows) if all(\n'
               '            x["ref_status"] == "clean" for x in rows[i:] if x["ref_status"] != "unknown")), None),')
        if t.count(old) != 1 or t.count("from hostsleep import host_sleep_s\n") != 1:
            raise RuntimeError("anchor for the convergence rule not found in heldout_eval.py")
        t = t.replace(old, '"first_ref_clean_t": first_stably_clean(rows),')
        t = t.replace("from hostsleep import host_sleep_s\n", "from hostsleep import host_sleep_s\n"
                      "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n"
                      "from r5g.verdict import first_stably_clean\n")
        open(ev, "w").write(t)
        if r.run("corrections_heldout_eval", [ev, os.path.join(cw, "results", "raw", "heldout")], os.path.join(cw, "testbed")) and \
           r.run("corrections_gen_rev25", [os.path.join(cw, "paper", "gen_macros.py"), cw, os.path.join(work, "corrections", "rev25")], cw):
            base = {x["key"]: x["value"] for x in csv.DictReader(open(gen + "/rev25/macros_rev25.csv"))}
            new = {x["key"]: x["value"] for x in csv.DictReader(open(os.path.join(work, "corrections", "rev25", "macros_rev25.csv")))}
            diff = {k: new[k] for k in new if base.get(k) != new[k]}
            os.makedirs(gen + "/corrections")
            with open(gen + "/corrections/corrections.tex", "w") as fh:
                fh.write("% check_values.py: rev25 keys that change under the stricter convergence rule\n")
                for k, v in sorted(diff.items()):
                    fh.write("\\expandafter\\def\\csname rx@%s\\endcsname{%s}%% corrected evidence-aware convergence\n" % (k, v))
            ok = True
    except Exception as e:
        print("  corrections failed: %s" % e)
    if not ok:
        r.steps.append({"step": "corrections", "returncode": "failed", "seconds": 0, "log": ""})

    # generated/macros.tex: the historical artifact's render.py, run on a copy (it writes ../../manuscript/generated).
    print("Regenerating the historical issue-study and timer macros", flush=True)
    hw = os.path.join(work, "historical", "artifact")
    shutil.copytree(HIST_SRC, hw, symlinks=True)
    if r.run("historical_render", ["render.py"], os.path.join(hw, "scripts")):
        shutil.copytree(os.path.join(work, "historical", "manuscript", "generated"), gen + "/historical")

    # Table "Reject-teardown reconstruction": the scorer of the earlier package on a copy of its retained records.
    print("Rescoring the reject-teardown reconstruction", flush=True)
    aw = os.path.join(work, "accumulation")
    shutil.copytree(ACC_SRC, aw, symlinks=True)
    reject_rows = None
    if r.run("reject_score", ["scripts/score_reject.py"], aw):
        rs = json.load(open(os.path.join(aw, "results", "reject-summary.json")))["arms"]
        reject_rows = ["%s & %d/%d & %d/%d & %d/%d \\\\" % (lab, rs[a]["fired"], rs[a]["valid"], rs[a]["signature_candidates"],
                       rs[a]["valid"], rs[a]["persistent_proxy"], rs[a]["valid"]) for a, lab in REJECT_ARMS]
        os.makedirs(gen + "/reject", exist_ok=True)
        open(gen + "/reject/tab_reject_rows.txt", "w").write("\n".join(reject_rows) + "\n")

    # Table "Matched checks on fresh runs" (supplementary appendix): render_validation.py of the earlier package.
    print("Re-rendering the fresh-validation table", flush=True)
    fresh_rows = None
    if r.run("validation_render", [os.path.join(ART, "reproduction", "render_validation.py"), "--input",
             os.path.join(ART, "reproduction", "evidence", "validation-20261126", "results"), "--out", gen + "/validation"], work):
        t = open(gen + "/validation/tab_fresh_validation.tex").read()
        seg = t[t.find("\\midrule") + len("\\midrule"):t.find("\\bottomrule")]
        fresh_rows = [l.strip() for l in seg.strip().splitlines() if l.strip()]

    # ------------------------------------------------------------------ compare
    exp = json.load(open(EXPECTED))
    regen_rx, regen_named = {}, {}
    for f, folder in ORDER:
        if folder is None:
            continue
        p = os.path.join(gen, folder, os.path.basename(f))
        if not os.path.exists(p):
            continue
        for k, v in parse_rx(p).items():
            regen_rx[k] = (v, f)
        if folder == "historical":
            regen_named.update(parse_named(p))
    report, counts = [], {}
    for row in exp["values"]:
        k, f, v = row["key"], row["defined_in"], row["value"]
        if row["kind"] == "named":
            g = regen_named.get(k) if f == "generated/macros.tex" else None
            reason = None if f == "generated/macros.tex" else NOT_REGENERABLE.get(f, "no generator")
        else:
            g = regen_rx.get(k, (None, None))[0]
            reason = NOT_REGENERABLE.get(f)
            if f == "generated-rev27/macros_rev27.tex" and k.startswith("ar-"):
                reason = AI_READER
        if reason:
            st = "not_regenerated"
        elif g is None:
            st = "missing"
        else:
            st = "match" if g == v else "mismatch"
        e = {"kind": row["kind"], "key": k, "used_in": row["used_in"], "defined_in": f, "expected": v, "obtained": g, "status": st}
        if reason:
            e["reason"] = reason
        report.append(e)
        counts.setdefault(row["used_in"], {}).setdefault(st, 0)
        counts[row["used_in"]][st] += 1
    extra_checks = []
    for name, folder in FIG.items():
        p = os.path.join(gen, folder, name)
        got = parse_defs(p) if os.path.exists(p) else {}
        for m, d in exp["figure_data"].items():
            if d["defined_in"].endswith(name):
                extra_checks.append({"item": "figure data " + m, "expected": d["value"], "obtained": got.get(m),
                                     "status": "match" if got.get(m) == d["value"] else ("missing" if m not in got else "mismatch")})
    for f, folder in TABLES.items():
        p = os.path.join(gen, folder, os.path.basename(f))
        got = body(p) if os.path.exists(p) else None
        want = exp["generated_text"][f]
        extra_checks.append({"item": "table body " + f, "expected": want, "obtained": got,
                             "status": "match" if got == want else ("missing" if got is None else "mismatch")})
    want = exp.get("literal_tables", {}).get("tab:reject-reconstruction")
    if want is not None:
        extra_checks.append({"item": "table rows tab:reject-reconstruction", "expected": want, "obtained": reject_rows,
                             "status": "match" if reject_rows == want else ("missing" if reject_rows is None else "mismatch")})
    want = exp.get("literal_tables", {}).get("tab:fresh-validation")
    if want is not None:
        extra_checks.append({"item": "table rows tab:fresh-validation", "expected": want, "obtained": fresh_rows,
                             "status": "match" if fresh_rows == want else ("missing" if fresh_rows is None else "mismatch")})
    bad = [e for e in report if e["status"] in ("mismatch", "missing")] + [e for e in extra_checks if e["status"] != "match"]
    summary = {"mode": "from-raw" if a.from_raw else "quick", "seconds": round(time.monotonic() - t_start, 1),
               "counts_by_document": counts,
               "regenerable_values": sum(1 for e in report if e["status"] != "not_regenerated"),
               "matched_values": sum(1 for e in report if e["status"] == "match"),
               "figure_and_table_checks": {"total": len(extra_checks), "matched": sum(e["status"] == "match" for e in extra_checks)},
               "failed_steps": [s for s in r.steps if s["returncode"] != 0]}
    json.dump({"summary": summary, "steps": r.steps, "values": report, "figure_and_table_checks": extra_checks},
              open(os.path.join(out, "quickcheck_report.json"), "w"), indent=1, ensure_ascii=False)
    lines = ["Recover5G quick check (%s), %.0f s" % (summary["mode"], summary["seconds"]), ""]
    for doc in sorted(counts):
        lines.append("%-12s %s" % (doc, ", ".join("%s %d" % (s, n) for s, n in sorted(counts[doc].items()))))
    lines.append("")
    lines.append("Regenerable paper values: %d of %d match" % (summary["matched_values"], summary["regenerable_values"]))
    lines.append("Figure data and generated tables: %d of %d match" % (summary["figure_and_table_checks"]["matched"], len(extra_checks)))
    if summary["failed_steps"]:
        lines.append("Failed steps: " + ", ".join(s["step"] for s in summary["failed_steps"]))
    if bad:
        lines.append("")
        lines.append("Differences:")
        for e in bad:
            if "key" in e:
                lines.append("  %-50s expected %-12s obtained %-12s (%s, %s)" % (e["key"], e["expected"], e["obtained"], e["used_in"], e["defined_in"]))
            else:
                lines.append("  %s: %s" % (e["item"], e["status"]))
    nr = {}
    for e in report:
        if e["status"] == "not_regenerated":
            nr[e["reason"]] = nr.get(e["reason"], 0) + 1
    if nr:
        lines.append("")
        lines.append("Not regenerated by this artifact:")
        for k, n in nr.items():
            lines.append("  %4d values: %s" % (n, k))
    txt = "\n".join(lines) + "\n"
    open(os.path.join(out, "quickcheck_summary.txt"), "w").write(txt)
    print("\n" + txt)
    if not a.keep_work:
        shutil.rmtree(work, ignore_errors=True)
    sys.exit(1 if bad or summary["failed_steps"] else 0)


if __name__ == "__main__":
    main()
