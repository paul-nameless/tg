#!/bin/bash

set -e

SRC=$(dirname $0)

cd $SRC

ARG=${1:-""}


case $ARG in
    build)
        python3 -m pip install --upgrade setuptools wheel
        python3 setup.py sdist bdist_wheel
        python3 -m pip install --upgrade twine
        python3 -m twine upload --repository testpypi dist/*
        ;;

    review)
        gh pr create -f
        ;;

    release)
        # CURRENT_VERSION=$(cat tg/__init__.py | grep version | cut -d '"' -f 2)
        CURRENT_VERSION=$(python3 -c 'import tg; print(tg.__version__, end="")')
        echo Current version $CURRENT_VERSION

        NEW_VERSION=$(echo $CURRENT_VERSION | awk -F. '{print $1 "." $2+1 "." $3}')
        echo New version $NEW_VERSION
        sed -i '' "s|$CURRENT_VERSION|$NEW_VERSION|g" tg/__init__.py

        git add -u tg/__init__.py
        git commit -m "Release v$NEW_VERSION"
        git tag v$NEW_VERSION

        flit publish
        git log --pretty=format:"%cn: %s" v$CURRENT_VERSION...v$NEW_VERSION  | grep -v -e "Merge" | grep -v "Release"| awk '!x[$0]++' > changelog.md
        git push origin master --tags
        gh release create v$NEW_VERSION -F changelog.md
        rm changelog.md
        ;;

    check)
        black .
        isort tg/*.py
        sh check.sh
        ;;

    *)
        python3 -m tg
        ;;
esac
