from setuptools import setup, find_packages

setup(
    name="msp-render-cli",
    version="0.1.0",
    description="Myers-Seth Pumps Deterministic Headless Render & Compositing CLI",
    author="Myers-Seth Pumps Engineering",
    packages=find_packages(),
    install_requires=[
        "numpy",
        "Pillow",
        "modal"
    ],
    entry_points={
        "console_scripts": [
            "msp-render=msp_render_cli.cli:main"
        ]
    }
)
