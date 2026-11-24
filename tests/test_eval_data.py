"""Sanity checks on the labelled test set.

Guards against the "taxonomy bug" found during the build: three test tickets were
labelled with a category the classifier can never output, so they were guaranteed
failures. These tests make that impossible to reintroduce.
"""

import json
import typing
from pathlib import Path

from agent import ClassificationResult
from ingest import KB_DIR

EVAL_FILE = Path(__file__).resolve().parent.parent / "data" / "eval" / "test_tickets.json"
TICKETS = json.loads(EVAL_FILE.read_text(encoding="utf-8"))

# The categories the classifier is allowed to output, read from its own schema.
CLASSIFIER_CATEGORIES = set(
    typing.get_args(ClassificationResult.model_fields["category"].annotation)
)


def test_test_set_has_20_tickets():
    assert len(TICKETS) == 20


def test_every_label_is_a_category_the_classifier_can_output():
    labels = {t["true_category"] for t in TICKETS}
    assert labels <= CLASSIFIER_CATEGORIES, labels - CLASSIFIER_CATEGORIES


def test_every_expected_article_exists_in_the_knowledge_base():
    for t in TICKETS:
        if t.get("expected_doc"):
            assert (Path(KB_DIR) / t["expected_doc"]).exists(), t["expected_doc"]
