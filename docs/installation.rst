Installation
============

pysmarthq requires Python 3.11 or newer and depends on aiohttp.

.. code-block:: bash

   pip install pysmarthq

From a checkout:

.. code-block:: bash

   pip install .

Development and tests:

.. code-block:: bash

   pip install -e ".[dev]"
   pytest

An editable checkout inside Home Assistant:

.. code-block:: bash

   pip3 install -e /path/to/pysmarthq
   hass --skip-pip-packages pysmarthq

Build the documentation
-----------------------

The documentation extra installs Sphinx and the Read the Docs theme. From a checkout:

.. code-block:: bash

   pip install -e ".[docs]"
   sphinx-build -W -b html docs docs/_build/html

Open ``docs/_build/html/index.html``. ``sphinx-build -W`` treats warnings as errors, which is the same bar as the Read the Docs configuration and the docs job in continuous integration.

Read the Docs
-------------

The published site is https://pysmarthq.readthedocs.io. Import this repository on `Read the Docs <https://about.readthedocs.com/>`_. The build uses :file:`.readthedocs.yaml` at the repository root:

* Ubuntu 24.04 and Python 3.12
* ``pip install .[docs]`` so autodoc imports this package
* Sphinx configuration at :file:`docs/conf.py`
* a failed build when Sphinx reports a warning

Read the Docs builds the default branch as ``latest`` and can activate versions for tags. No extra dashboard overrides are required for the HTML build.
