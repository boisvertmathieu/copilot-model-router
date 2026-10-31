PYTHON ?= python3

.PHONY: test refresh route-demo

test:
	$(PYTHON) -m unittest discover -s tests

refresh:
	PYTHON="$(PYTHON)" bash scripts/refresh.sh $(REFRESH_ARGS)

route-demo:
	$(PYTHON) scripts/route.py --role doc --story "Corriger une typo dans la doc" --files 1 --pane 1
	$(PYTHON) scripts/route.py --role dev --story "Refactor multi-modules" --diff-stats "12 files changed, 340 insertions(+), 80 deletions(-)" --pane 2
	$(PYTHON) scripts/route.py --role e2e-validator --story "Valider la feature" --dev-model claude-sonnet-5.5 --pane 3
