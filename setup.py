from setuptools import setup, find_packages

setup(
    name="msp-render-cli",
    version="0.2.0",
    description="Myers-Seth Pumps deterministic headless render & compositing CLI",
    author="Myers-Seth Pumps Engineering",
    python_requires=">=3.11",
    packages=find_packages(exclude=["archive", "archive.*", "tests"]),
    py_modules=["composite_worker", "render_worker"],
    install_requires=[
        "numpy",
        "Pillow",
    ],
    extras_require={
        # Only needed for `dispatch-modal`; local rendering does not import it.
        "cloud": ["modal"],
    },
    entry_points={
        "console_scripts": [
            "msp-render=msp_render_cli.cli:main"
        ]
    },
)
