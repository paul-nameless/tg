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
        CURRENT_VERSION=$(cat tg/__init__.py | grep version | cut -d '"' -f 2)
        echo Current version $CURRENT_VERSION

        NEW_VERSION=$(echo $CURRENT_VERSION | awk -F. '{print $1 "." $2+1 "." $3}')
        echo New version $NEW_VERSION
        sed -i '' "s|$CURRENT_VERSION|$NEW_VERSION|g" tg/__init__.py
        poetry version $NEW_VERSION

        git add -u tg/__init__.py pyproject.toml
        git commit -m "Release v$NEW_VERSION"
        git tag v$NEW_VERSION

        poetry build
        poetry publish -u $(pass show i/pypi | grep username | cut -d ' ' -f 2 | tr -d '\n') -p $(pass show i/pypi | head -n 1 | tr -d '\n')
        git log --pretty=format:"%cn: %s" v$CURRENT_VERSION...v$NEW_VERSION  | grep -v -e "Merge" | grep -v "Release"| awk '!x[$0]++' > changelog.md
        git push origin master --tags
        gh release create v$NEW_VERSION -F changelog.md
        rm changelog.md
        ;;

    release-brew)
        CURRENT_VERSION=$(cat tg/__init__.py | grep version | cut -d '"' -f 2)
        echo Current version $CURRENT_VERSION

        URL="https://github.com/paul-nameless/tg/archive/refs/tags/v$CURRENT_VERSION.tar.gz"
        echo $URL
        wget $URL -O /tmp/tg.tar.gz
        HASH=$(sha256sum /tmp/tg.tar.gz | cut -d ' ' -f 1)
        rm /tmp/tg.tar.gz

        cd /opt/homebrew/Library/Taps/paul-nameless/homebrew-repo
        sed -i '' "6s|.*|  url \"https://github.com/paul-nameless/tg/archive/refs/tags/v$CURRENT_VERSION.tar.gz\"|" tg.rb
        sed -i '' "7s|.*|  sha256 \"$HASH\"|" tg.rb

        brew audit --new tg
        brew uninstall tg || true
        brew install tg
        brew test tg

        git add -u tg.rb
        git commit -m "Release tg.rb v$CURRENT_VERSION"
        git push origin master
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
