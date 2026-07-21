from IPython import get_ipython
from IPython.core.magic import register_cell_magic

print('Notebook setup.')

get_ipython().run_line_magic('reload_ext', 'autoreload')
get_ipython().run_line_magic('autoreload', '2')
try:
    get_ipython().run_line_magic('matplotlib', 'inline')
except ImportError:
    pass


@register_cell_magic
def skipcell(line=None, cell=None):
    print("skipping this cell...")
    return

def get_current_interpreter_path():
    import sys
    print(f"Current Python interpreter path: {sys.executable}")


get_current_interpreter_path()


# pd.options.display.max_columns = None  # Show all columns
# pd.options.display.max_rows = None  # Show all rows
# pd.options.display.max_colwidth = None  # Show full content in each cell
