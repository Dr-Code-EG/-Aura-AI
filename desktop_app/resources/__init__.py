"""Package marker so ``importlib.resources.files`` can locate bundled assets.

PyInstaller's frozen builds need this to be a real package (not a namespace
package) so that ``resources.files("desktop_app.resources")`` resolves
correctly. The actual data file is :file:`chatgpt_inject.js`.
"""
