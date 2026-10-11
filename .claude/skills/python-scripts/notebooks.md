# Notebooks

### A notebook is restarted and run top to bottom before its result is shared

**Why:** cells run out of order leave state no reader can reproduce — a variable from a deleted
cell, a dataframe filtered twice — and a notebook whose result depends on it has no result.
Executing it headless from a clean kernel is the check.

**Example:**
```bash
# WRONG — committed with whatever state the session happened to reach
git add churn_by_cohort.ipynb

# CORRECT — executed from a fresh kernel first; a cell that depended on lost state fails here
jupyter nbconvert --to notebook --execute --inplace churn_by_cohort.ipynb
git add churn_by_cohort.ipynb
```

### Outputs that hold a token or a customer's row are cleared before the notebook is committed

**Why:** outputs are part of the `.ipynb` file; a printed token or a displayed row of customer data
is committed and pushed with it, and stays in the history after the cell is fixed.

**Example:**
```bash
# WRONG — the printed API token and the displayed customer rows go into the repository
git add churn_by_cohort.ipynb

# CORRECT — the outputs are cleared; the code that produces them is what is committed
jupyter nbconvert --clear-output --inplace churn_by_cohort.ipynb
git add churn_by_cohort.ipynb
```

### Code that survives the exploration moves to a module the notebook imports

**Why:** a function copied from one notebook into the next is a module not yet written, and each
copy drifts on its own. In the module the full rules apply, and it can be tested.

**Example:**
```python
# WRONG — the cleaning function is pasted into each new notebook, and the copies drift
def drop_trial_accounts(accounts: pd.DataFrame) -> pd.DataFrame:
    return accounts[accounts["plan"] != "trial"]


# CORRECT — defined once in the package, imported by every notebook
from churn.cleaning import drop_trial_accounts
```
