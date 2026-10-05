"""Spec 09 classifier set: draft generation and human review (AC-04, AC-10; ADR 0025).

Offline: a fake client stands in for Bedrock, so no test calls a real model. The committed drafts, when present, are
checked for their fields and author rule; the promoted split files are not created here (they come after review).
"""
from __future__ import annotations

import csv
import itertools
import json
import re
from collections import Counter
from pathlib import Path

import pytest

from eval.classifier import generate as gen
from eval.classifier import review
from nick_of_time.llm import LLMResult, ProviderUnavailable
from nick_of_time.nlu.dates import parse_date
from nick_of_time.policy.clock import DEMO_TODAY
from tests.test_spec11_protocol import _check_split_rows, _manifest_hash, _split_files

ROOT = Path(__file__).resolve().parents[1]
DRAFTS = ROOT / "eval" / "classifier" / "draft"
FIELDS = ["id", "text", "language", "intent", "also_dispute", "slots", "card", "author", "source", "generator",
          "seed_id", "origin", "prompt_hash", "persona", "checks", "review_status"]
SLOTS = {"amount", "currency", "date", "merchant"}


class FakeModel:
    """Answers seed and paraphrase prompts from the prompt itself: every quoted item of a brief (or of the keep rule)
    goes into the message, plus a neutral filler in the prompt's language. `drop` lists 1-based line numbers that the
    first answer leaves out, to exercise the retry. Never touches the network."""

    def __init__(self, model="fake", drop=(), fail_first=0):
        self.model, self.drop, self.fail_first, self.calls = model, set(drop), fail_first, []
        self._names = ("".join(p) for n in itertools.count(2) for p in itertools.product("bcdfghjklmnpqrstvz", repeat=n))

    def complete(self, system, user, *, max_tokens=512, **_):
        self.calls.append(user)
        if self.fail_first:
            self.fail_first -= 1
            raise ProviderUnavailable("ThrottlingException: slow down")
        n = int(re.search(r"Answer with exactly (\d+) lines", user).group(1))
        pt = "Portuguese" in user.split("\n", 1)[0] or "in Portuguese" in user
        filler = "olá, preciso de ajuda com essa cobrança, obrigado, ref" if pt else "hola, necesito ayuda con este cargo, gracias, ref"
        if "Rewrite it" in user:
            keep = re.search(r"Keep these exactly as written: (.*?)\.(?: |$)", user)
            quoted = [re.findall(r'"([^"]+)"', keep.group(1)) if keep else []] * n
        else:
            briefs = dict(re.findall(r"^(\d+)\. Customer: (.*)$", user, re.M))
            quoted = [re.findall(r'"([^"]+)"', briefs[str(i)]) for i in range(1, n + 1)]
        lines = [f"{i}. {' '.join(q)} {filler} {next(self._names)}" for i, q in enumerate(quoted, 1)
                 if not (i in self.drop and len(self.calls) == 1)]
        text = "Here you go:\n" + "\n".join(lines)
        return LLMResult(text=text, tool_input=None, stop_reason="end_turn", tokens_in=len(user) // 4,
                         tokens_out=len(text) // 4, cost_usd=0.0001, provider="fake", model=self.model, mode=None,
                         temperature=gen.TEMPERATURE, latency_ms=1)


@pytest.fixture(scope="module")
def validation_rows():
    rows, record = gen.run_split("validation", FakeModel(), workers=1, sleep=lambda s: None)
    return rows, record


# --- plan, prompts and generators ------------------------------------------------------------------------------------

def test_ac_04_plan_order_and_prompt_hash_are_deterministic():
    for split in gen.SPLITS:
        a, b = gen.build_plan(split), gen.build_plan(split)
        assert a == b and gen.plan_hash(a) == gen.plan_hash(b)
        assert [gen.seed_prompt(x) for x in gen._seed_batches(a)] == [gen.seed_prompt(x) for x in gen._seed_batches(b)]
    assert gen.build_plan("train", seed=1) != gen.build_plan("train")
    assert re.fullmatch(r"[0-9a-f]{64}", gen.PROMPT_HASH) and gen.PROMPT_HASH == gen._prompt_hash()


def test_ac_04_prompt_hash_changes_with_the_prompt_text(monkeypatch):
    before = gen._prompt_hash()
    monkeypatch.setitem(gen.RULES, "no_dispute", "Do not report any charge at all.")
    assert gen._prompt_hash() != before
    monkeypatch.setattr(gen, "PROMPT_VERSION", "cls-gen-v999")
    assert gen._prompt_hash() != before


def test_ac_04_limit_plans_the_same_items_as_a_full_run():
    full = gen.build_plan("test")
    short = gen.build_plan("test", limit=1)
    firsts = [next(i for i in full if i["cell"] == c) for c in dict.fromkeys(i["cell"] for i in full)]
    strip = [{k: v for k, v in i.items() if k != "id"} for i in firsts]
    assert [{k: v for k, v in i.items() if k != "id"} for i in short] == strip


def test_ac_04_one_generator_family_per_split_and_no_claude():
    """ADR 0025: train Llama, validation Gemma, test DeepSeek; different families; none is Claude."""
    gens = gen.GENERATORS
    assert set(gens) == set(gen.SPLITS)
    assert len({g.family for g in gens.values()}) == 3 and len({g.model_id for g in gens.values()}) == 3
    for g in gens.values():
        assert not re.search(r"anthropic|claude", f"{g.model_id} {g.family}", re.I)
    assert gens["train"].model_id == "us.meta.llama3-3-70b-instruct-v1:0"
    assert gens["validation"].model_id == "google.gemma-3-27b-it"
    assert gens["test"].model_id == "deepseek.v3.2"
    prices = gen.load_prices()
    assert all(g.price_key in prices for g in gens.values())


def test_ac_04_prompts_ask_for_plain_text_and_planned_slots():
    item = next(i for i in gen.build_plan("train") if i["slots"]["amount"] and i["card"]["kind"] == "generic")
    prompt = gen.seed_prompt([item])
    assert f'"{item["slots"]["amount"]["text"]}"' in prompt and f'"{item["card"]["text"]}"' in prompt
    assert "Do not say whether the card is debit or credit." in prompt
    assert "Answer with exactly 1 lines" in prompt and "json" not in prompt.lower()
    para = gen.paraphrase_prompt(item, "texto", item["paraphrases"])
    assert "Keep these exactly as written" in para and f'"{item["slots"]["amount"]["text"]}"' in para


# --- targets ---------------------------------------------------------------------------------------------------------

def test_ac_04_draft_targets_overgenerate_every_cell_and_keep_the_shares():
    """Final 48/12/20 per language × intent and per split for injection (spec 09 §7.6), drafted about 20% above."""
    assert gen.FINAL_PER_CELL == {"train": 48, "validation": 12, "test": 20}
    assert gen.DRAFT_PER_CELL == {"train": 58, "validation": 15, "test": 24}
    totals = {}
    for split in gen.SPLITS:
        items = gen.build_plan(split)
        per_cell = Counter()
        for i in items:
            per_cell[i["cell"]] += 1 + len(i["paraphrases"])
        assert set(per_cell.values()) == {gen.DRAFT_PER_CELL[split]}, (split, per_cell)
        assert len(per_cell) == len(gen.LANGS) * len(gen.INTENTS) + 1
        assert all(len(i["paraphrases"]) <= gen.PARAPHRASES_PER_SEED for i in items)
        totals[split] = sum(per_cell.values())
    total = sum(totals.values())
    assert total == 1067
    for split, share in review.SHARES.items():
        assert abs(totals[split] / total - share) <= 0.01, split
        assert gen.DRAFT_PER_CELL[split] >= gen.FINAL_PER_CELL[split] * (1 + gen.MARGIN) - 1
    final = {s: n * 11 for s, n in gen.FINAL_PER_CELL.items()}
    assert {s: n / sum(final.values()) for s, n in final.items()} == pytest.approx(review.SHARES)
    assert gen.FINAL_PER_CELL["test"] * len(gen.INTENTS) >= review.MIN_TEST_PER_LANGUAGE   # 100 per language


def test_ac_04_injection_and_also_dispute_are_planned():
    items = gen.build_plan("train")
    inj = [i for i in items if i["label"] == "injection"]
    assert inj and all(i["intent"] is None for i in inj)
    assert {i["language"] for i in inj} == set(gen.LANGS)
    assert any(i["persona"]["code_switch"] for i in inj)
    also = [i for i in items if i["also_dispute"]]
    assert {i["intent"] for i in also} == {"status_inquiry", "human_request"}
    assert all(i["slots"] == {"amount": None, "date": None, "merchant": None}
               for i in items if i["intent"] == "out_of_scope" or i["label"])


def test_ac_04_planned_dates_agree_with_the_b0_date_parser():
    """Slot dates are resolved against DEMO_TODAY with the convention of spec 11 AC-08."""
    seen = 0
    for split in gen.SPLITS:
        for i in gen.build_plan(split):
            d = i["slots"]["date"]
            if d:
                assert parse_date(d["text"], DEMO_TODAY).isoformat() == d["value"], d
                seen += 1
    assert seen > 50


# --- rows ------------------------------------------------------------------------------------------------------------

def test_ac_04_ac_10_rows_have_the_fields_and_the_author_rule(validation_rows):
    rows, record = validation_rows
    model = gen.GENERATORS["validation"].model_id
    by_id = {r["id"]: r for r in rows}
    assert len(by_id) == len(rows) == 165
    for r in rows:
        assert [k for k in r if k != "label"] == FIELDS
        assert set(r["slots"]) == SLOTS
        assert r["review_status"] == "pending" and r["prompt_hash"] == gen.PROMPT_HASH
        assert r["author"] == r["generator"] == r["origin"] == model
        assert r["language"] in gen.LANGS
        if r.get("label") == "injection":
            assert r["intent"] is None
        else:
            assert "label" not in r and r["intent"] in gen.INTENTS
        if r["also_dispute"]:
            assert r["intent"] in ("status_inquiry", "human_request")
        if r["source"] == "written":
            assert r["seed_id"] is None
        else:
            assert r["source"] == "paraphrase"
            seed = by_id[r["seed_id"]]
            assert seed["source"] == "written" and seed["author"] == r["author"]   # AC-10
            assert (seed["intent"], seed.get("label"), seed["slots"]) == (r["intent"], r.get("label"), r["slots"])
    assert record["model_id"] == model and record["temperature"] == gen.TEMPERATURE
    assert record["prompt_hash"] == gen.PROMPT_HASH and record["seed"] == gen.SEED
    assert record["counts"]["rows"] == 165 and not record["failures"]
    assert set(record["counts"]["by_language_intent"].values()) == {15}
    assert sum(record["counts"]["injection_by_language"].values()) == 15


def test_ac_04_clean_fake_output_raises_no_check(validation_rows):
    rows, _ = validation_rows
    flagged = [(r["id"], r["checks"], r["text"]) for r in rows if r["checks"]]
    assert not flagged, flagged[:5]


def test_ac_04_rows_are_deterministic_for_a_fixed_fake():
    a, _ = gen.run_split("validation", FakeModel(), workers=1, sleep=lambda s: None, limit=1)
    b, _ = gen.run_split("validation", FakeModel(), workers=1, sleep=lambda s: None, limit=1)
    assert a == b


# --- checker ---------------------------------------------------------------------------------------------------------

def _item(card_kind="generic", card="mi tarjeta", amount=True, date=True, merchant="Rappi", intent="unrecognized_charge",
          lang="es", also=False):
    return {
        "language": lang, "intent": intent, "label": None, "also_dispute": also,
        "slots": {"amount": {"text": "1,250 pesos", "number": "1,250", "currency_text": "pesos", "value": "1250",
                             "currency": None} if amount else None,
                  "date": {"text": "ayer", "check": r"\bayer\b", "value": "2026-05-31"} if date else None,
                  "merchant": merchant},
        "card": {"kind": card_kind, "text": card},
    }


P = {"code_switch": False}


def test_ac_04_checker_flags_card_type_drift():
    """The example of ADR 0025: "mi tarjeta" became "mi tarjeta de crédito"."""
    item = _item()
    assert gen.check_text("Ayer me cobraron 1,250 pesos en Rappi con mi tarjeta y no fui yo", item, P) == []
    drift = gen.check_text("Ayer me cobraron 1,250 pesos en Rappi con mi tarjeta de crédito y no fui yo", item, P)
    assert "unplanned_card_type" in drift
    debit = _item("debit", "mi tarjeta de débito")
    assert gen.check_text("ayer 1,250 pesos en Rappi con mi tarjeta de débito, no lo reconozco", debit, P) == []
    assert {"card_missing", "unplanned_card_type"} <= set(
        gen.check_text("ayer 1,250 pesos en Rappi con mi tarjeta de crédito, no lo reconozco", debit, P))
    status = _item(intent="status_inquiry", amount=False, date=False, merchant=None)
    assert gen.check_text("¿cuándo llega el crédito provisional a mi tarjeta?", status, P) == []


def test_ac_04_checker_flags_slot_drift():
    item = _item()
    flags = gen.check_text("Me cobraron 12,500 dólares en Uber el viernes con mi tarjeta", item, P)
    assert {"amount_missing", "currency_missing", "date_missing", "merchant_missing", "unplanned_merchant"} <= set(flags)
    bare = _item(amount=False, date=False, merchant=None)
    assert {"unplanned_amount", "unplanned_date"} <= set(
        gen.check_text("no reconozco un cargo de 300 pesos de hoy en mi tarjeta", bare, P))
    assert "quoted_slot" in gen.check_text('Ayer me cobraron 1,250 pesos en "Rappi" con mi tarjeta', item, P)


def test_ac_04_checker_flags_language_dispute_and_format_drift():
    item = _item(amount=False, date=False, merchant=None)
    assert "language_drift" in gen.check_text("Não reconheço essa compra no meu cartão, você pode ajudar?", item, P)
    assert "english_drift" in gen.check_text("I do not know this charge on my card, please help with the account",
                                             item, P)
    assert gen.check_text("I do not know this charge on my card, please", item, {"code_switch": True}).count(
        "english_drift") == 0
    human = _item(intent="human_request", amount=False, date=False, merchant=None, card_kind="none", card=None)
    assert "unplanned_dispute" in gen.check_text("quiero hablar con alguien, no reconozco un cargo", human, P)
    also = _item(intent="human_request", amount=False, date=False, merchant=None, card_kind="none", card=None,
                 also=True)
    assert "dispute_missing" in gen.check_text("quiero hablar con una persona ya", also, P)
    assert "too_short" in gen.check_text("hola", item, P)
    assert "same_as_seed" in gen.check_text("Hola, mi tarjeta", item, P, seed_text="hola, mi  tarjeta")


# --- parsing and retries ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("answer,expected", [
    ("Here are the messages:\n1. Hola uno\n2. Hola dos\n3. Hola tres", {1: "Hola uno", 2: "Hola dos", 3: "Hola tres"}),
    ('1) "Hola uno"\n2) “Hola dos”\n3) Hola tres', {1: "Hola uno", 2: "Hola dos", 3: "Hola tres"}),
    ("**1.** Hola uno\n**2.** Hola dos\n**3.** Hola tres", {1: "Hola uno", 2: "Hola dos", 3: "Hola tres"}),
    ("```\n1. Hola uno\n\n2. Hola dos\n3. Hola tres\n```", {1: "Hola uno", 2: "Hola dos", 3: "Hola tres"}),
    ('["Hola uno", "Hola dos", "Hola tres"]', {1: "Hola uno", 2: "Hola dos", 3: "Hola tres"}),
    ("<think>plan</think>\n1. Hola uno\n2. Hola dos\n3. Hola tres", {1: "Hola uno", 2: "Hola dos", 3: "Hola tres"}),
    ("Hola uno\nHola dos\nHola tres", {1: "Hola uno", 2: "Hola dos", 3: "Hola tres"}),
    ("1. Hola uno\n3. Hola tres\n4. sobra", {1: "Hola uno", 3: "Hola tres"}),
    ("1. Mensaje: Hola uno\n2. Customer: formal. Situation: x\n3. - Hola tres", {1: "Hola uno", 3: "- Hola tres"}),
    ("Lo siento, no puedo ayudar con eso.", {}),
])
def test_ac_04_parses_messy_model_output(answer, expected):
    assert gen.parse_numbered(answer, 3) == expected


def test_ac_04_ask_re_asks_only_missing_items_and_is_bounded():
    usage = gen.Usage()
    model = FakeModel(drop={2})
    got = gen.ask(model, 3, lambda idx: gen.SEED_TEMPLATE.format(
        n=len(idx), language="Spanish", definition="x", briefs="\n".join(
            f'{k}. Customer: c. Situation: s. Include the merchant "M{i}".' for k, i in enumerate(idx, 1))), usage)
    assert sorted(got) == [0, 1, 2] and "M1" in got[1] and len(model.calls) == 2
    assert "Answer with exactly 1 lines" in model.calls[1]

    class Silent(FakeModel):
        def complete(self, system, user, **kw):
            self.calls.append(user)
            return LLMResult("no puedo", None, "end_turn", 1, 1, 0.0, "fake", "m", None, 0.9, 1)

    silent = Silent()
    assert gen.ask(silent, 2, lambda idx: "x", gen.Usage()) == {} and len(silent.calls) == gen.MAX_ATTEMPTS


def test_ac_04_ask_waits_and_retries_on_provider_errors():
    usage, waits = gen.Usage(), []
    got = gen.ask(FakeModel(fail_first=1), 1, lambda idx: gen.SEED_TEMPLATE.format(
        n=1, language="Spanish", definition="x", briefs="1. Customer: c. Situation: s."), usage, sleep=waits.append)
    assert 0 in got and waits == [1] and len(usage.errors) == 1


# --- cost guard, files and CLI ---------------------------------------------------------------------------------------

def test_ac_04_cost_guard_stops_before_any_call(monkeypatch, capsys):
    def boom(*a, **k):
        raise AssertionError("a model client was built")
    monkeypatch.setattr(gen, "bedrock_client", boom)
    assert gen.main(["--dry-run"]) == 0
    assert gen.main(["--max-usd", "0.0001"]) == 2
    out = capsys.readouterr().out
    assert gen.PROMPT_HASH in out and "projected total" in out
    total = sum(gen.projected_cost(s, gen.load_prices()) for s in gen.SPLITS)
    assert 0 < total < gen.MAX_USD


def test_ac_04_main_writes_drafts_with_a_fake_client(monkeypatch, tmp_path):
    monkeypatch.setattr(gen, "bedrock_client", lambda split, prices, profile, region: FakeModel())
    assert gen.main(["--splits", "test", "--limit", "1", "--workers", "1", "--out", str(tmp_path)]) == 0
    rows = [json.loads(x) for x in (tmp_path / "test.jsonl").read_text().splitlines()]
    run = json.loads((tmp_path / "generation.json").read_text())
    assert len(rows) == 44 and run["splits"]["test"]["model_id"] == "deepseek.v3.2"
    assert run["prompt_hash"] == gen.PROMPT_HASH and run["label"] == "[simulated]"
    assert run["slot_dates_resolved_against"] == DEMO_TODAY.isoformat()


def test_ac_04_drafts_in_a_subfolder_are_not_split_files(tmp_path):
    """Seal (b) hashes top-level eval/classifier/*.jsonl only, so drafts never enter the manifest."""
    d = tmp_path / "eval" / "classifier" / "draft"
    d.mkdir(parents=True)
    (d / "train.jsonl").write_text('{"text": "a"}\n')
    assert _split_files(tmp_path) == []


# --- committed drafts ------------------------------------------------------------------------------------------------

def _committed():
    return {s: [json.loads(x) for x in (DRAFTS / f"{s}.jsonl").read_text().splitlines() if x.strip()]
            for s in gen.SPLITS if (DRAFTS / f"{s}.jsonl").exists()}


def test_ac_04_ac_10_committed_drafts_follow_the_author_rule():
    drafts = _committed()
    if not drafts:
        pytest.skip("no committed drafts")
    run = json.loads((DRAFTS / "generation.json").read_text())
    authors = {}
    for split, rows in drafts.items():
        by_id = {r["id"]: r for r in rows}
        assert len(by_id) == len(rows), split
        authors[split] = {r["author"] for r in rows}
        assert authors[split] == {gen.GENERATORS[split].model_id}, split
        assert run["splits"][split]["model_id"] == gen.GENERATORS[split].model_id
        assert run["splits"][split]["counts"]["rows"] == len(rows)
        for r in rows:
            assert [k for k in r if k != "label"] == FIELDS, r["id"]
            assert r["review_status"] == "pending" and r["prompt_hash"] == run["splits"][split]["prompt_hash"]
            assert (r["intent"] is None) == (r.get("label") == "injection")
            if r["source"] == "paraphrase":
                assert by_id[r["seed_id"]]["author"] == r["author"]
    for a, b in itertools.combinations(authors, 2):
        assert not authors[a] & authors[b]


def test_ac_04_committed_drafts_hold_no_label_from_gold_eval():
    for path in [*DRAFTS.glob("*.jsonl"), *DRAFTS.glob("*.json"), ROOT / "eval/classifier/generate.py",
                 ROOT / "eval/classifier/review.py"]:
        if path.exists():
            text = path.read_text()
            assert "gold_eval" not in text and "is_fraud" not in text, path.name


# --- review: export and promote --------------------------------------------------------------------------------------

def _drafts_in(tmp_path) -> Path:
    """Three small fake splits in a tmp repo: draft files only, as after generation."""
    root = tmp_path
    out = root / "eval" / "classifier" / "draft"
    for split in gen.SPLITS:
        rows, record = gen.run_split(split, FakeModel(), workers=1, sleep=lambda s: None)
        gen.write_split(out, split, rows, record)
    return root


@pytest.fixture(scope="module")
def drafted(tmp_path_factory):
    return _drafts_in(tmp_path_factory.mktemp("repo"))


def _read_csv(path):
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=review.CSV_FIELDS)
        w.writeheader()
        w.writerows(rows)


def _decide(root, reviewers=None, edit=None):
    reviewers = reviewers or {"train": "@salazarvalverdeai", "validation": "@salazarvalverdeai", "test": "@gianzk"}
    for split in gen.SPLITS:
        path = review.export(root, split, force=True)
        rows = _read_csv(path)
        for r in rows:
            r["decision"], r["reviewer"] = "keep", reviewers[split]
        if edit:
            edit(split, rows)
        _write_csv(path, rows)


def test_ac_04_export_writes_one_csv_row_per_draft_and_refuses_to_overwrite(tmp_path):
    root = tmp_path
    rows, record = gen.run_split("validation", FakeModel(), workers=1, sleep=lambda s: None, limit=1)
    gen.write_split(root / "eval/classifier/draft", "validation", rows, record)
    path = review.export(root, "validation")
    assert path == root / "eval/classifier/draft/review_validation.csv"
    got = _read_csv(path)
    assert [r["id"] for r in got] == [r["id"] for r in rows]
    assert list(got[0]) == review.CSV_FIELDS and all(r["decision"] == "" for r in got)
    with pytest.raises(review.ReviewError):
        review.export(root, "validation")


def test_ac_04_promote_writes_top_level_splits_that_pass_spec11(drafted, tmp_path):
    """AC-04: the promoted set has the author split, the shares and the test minimums of spec 11 AC-06."""
    root = _copy_drafts(drafted, tmp_path)

    def edit(split, rows):
        if split == "train":
            rows[0]["decision"], rows[0]["fixed_text"], rows[0]["fixed_card"] = "fix", "texto corregido", "mi tarjeta"
            rows[1]["decision"] = "drop"
            rows[2]["decision"], rows[2]["fixed_amount"] = "fix", "null"

    _decide(root, edit=edit)
    result = review.promote(root)
    files = _split_files(root)
    assert [f.name for f in files] == ["test.jsonl", "train.jsonl", "validation.jsonl"]
    assert result["manifest_sha256"] == _manifest_hash(files, root)
    rows = {s: [json.loads(x) for x in (root / f"eval/classifier/{s}.jsonl").read_text().splitlines()]
            for s in gen.SPLITS}
    _check_split_rows(rows)                                  # the same check spec 11 runs on the real files
    train = {r["id"]: r for r in rows["train"]}
    drafts = [json.loads(x) for x in (root / "eval/classifier/draft/train.jsonl").read_text().splitlines()]
    fixed, dropped, nulled = drafts[0], drafts[1], drafts[2]
    assert train[fixed["id"]]["text"] == "texto corregido" and train[fixed["id"]]["review_status"] == "fixed"
    assert train[fixed["id"]]["original"]["text"] == fixed["text"]
    assert train[fixed["id"]]["card"] == "mi tarjeta" and train[fixed["id"]]["reviewer"] == "@salazarvalverdeai"
    assert dropped["id"] not in train
    assert train[nulled["id"]]["slots"]["amount"] is None
    assert train[nulled["id"]]["original"]["slots"] == nulled["slots"]
    kept = next(r for r in rows["test"])
    assert kept["review_status"] == "kept" and "checks" not in kept and "original" not in kept


def test_ac_04_promote_refuses_rows_without_a_decision(drafted, tmp_path):
    def edit(split, rows):
        if split == "validation":
            rows[3]["decision"] = ""
    root = _copy_drafts(drafted, tmp_path)
    _decide(root, edit=edit)
    with pytest.raises(review.ReviewError, match="decision"):
        review.promote(root)
    assert not _split_files(root)


def test_ac_04_promote_refuses_a_test_split_reviewed_by_the_classifier_developer(drafted, tmp_path):
    """ADR 0025: the test split is reviewed by someone who is not the classifier's developer."""
    root = _copy_drafts(drafted, tmp_path)
    _decide(root, reviewers={"train": "@salazarvalverdeai", "validation": "@salazarvalverdeai",
                             "test": "salazarvalverdeai"})
    with pytest.raises(review.ReviewError, match="classifier developer"):
        review.promote(root)
    assert not _split_files(root)


@pytest.mark.parametrize("edit,match", [
    (lambda s, rows: rows[0].update(decision="maybe"), "decision"),
    (lambda s, rows: rows[0].update(decision="fix"), "fix"),
    (lambda s, rows: rows[0].update(reviewer=""), "reviewer"),
    (lambda s, rows: rows[0].update(decision="fix", fixed_intent="loan"), "intent"),
    (lambda s, rows: rows[0].update(decision="fix", fixed_amount="12,5"), "amount"),
    (lambda s, rows: rows.pop(), "missing"),
])
def test_ac_04_promote_refuses_bad_review_rows(drafted, tmp_path, edit, match):
    root = _copy_drafts(drafted, tmp_path)
    _decide(root, edit=lambda s, rows: edit(s, rows) if s == "train" else None)
    with pytest.raises(review.ReviewError, match=match):
        review.promote(root)


def test_ac_04_promote_refuses_shares_or_minimums_out_of_range(drafted, tmp_path):
    root = _copy_drafts(drafted, tmp_path)

    def edit(split, rows):
        if split == "test":   # 24 drafts in the cell; dropping 5 leaves 19, below the minimum of 20
            for r in [r for r in rows if r["language"] == "pt" and r["intent"] == "human_request"][:5]:
                r["decision"] = "drop"
    _decide(root, edit=edit)
    with pytest.raises(review.ReviewError, match="per intent"):
        review.promote(root)
    assert not _split_files(root)
    _decide(root, edit=lambda s, rows: [r.update(decision="drop") for r in rows[: len(rows) // 2]] if s == "train" else 0)
    with pytest.raises(review.ReviewError, match="share of train"):
        review.promote(root)


def test_ac_04_promote_dry_run_writes_nothing_and_refuses_a_sealed_protocol(drafted, tmp_path):
    root = _copy_drafts(drafted, tmp_path)
    _decide(root)
    result = review.promote(root, dry_run=True)
    assert not _split_files(root) and re.fullmatch(r"[0-9a-f]{64}", result["manifest_sha256"])
    (root / "eval" / "PROTOCOL.md").write_text("<!-- SEAL:BEGIN -->\n- Status: SEALED\n<!-- SEAL:END -->\n")
    with pytest.raises(review.ReviewError, match="sealed"):
        review.promote(root)


def _copy_drafts(drafted, tmp_path) -> Path:
    import tempfile
    root = Path(tempfile.mkdtemp(prefix="cls-review-"))
    for split in gen.SPLITS:
        dst = root / "eval/classifier/draft" / f"{split}.jsonl"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text((drafted / "eval/classifier/draft" / f"{split}.jsonl").read_text())
    return root
