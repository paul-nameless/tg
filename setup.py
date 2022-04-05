import tg
from setuptools import setup

with open("readme.md", "r") as fh:
    readme = fh.read()


setup(
    long_description=readme,
    long_description_content_type="text/markdown",
    name="tg",
    version=tg.__version__,
    description="Terminal client for telegram",
    url="https://github.com/paul-nameless/tg",
    author="Paul Nameless",
    author_email="reacsdas@gmail.com",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
    packages=["tg"],
    entry_points={"console_scripts": ["tg = tg.__main__:main"]},
    python_requires=">=3.8",
    install_requires=["python-telegram==0.15.0"],
)
