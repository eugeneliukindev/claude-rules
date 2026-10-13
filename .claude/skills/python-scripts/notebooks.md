# Notebooks

### A notebook is restarted and run top to bottom before its result is shared

**Why:** cells run out of order leave state no reader can reproduce — a variable from a deleted
cell, a dataframe filtered twice — and a notebook whose result depends on it has no result.
Executing it headless from a clean kernel is the check.

### Outputs that hold a token or a customer's row are cleared before the notebook is committed

**Why:** outputs are part of the `.ipynb` file; a printed token or a displayed row of customer data
is committed and pushed with it, and stays in the history after the cell is fixed.

### Code that survives the exploration moves to a module the notebook imports

**Why:** a function copied from one notebook into the next is a module not yet written, and each
copy drifts on its own. In the module the full rules apply, and it can be tested.
