# tg

Console telegram client.

(!) currently it is in active development


## Usage

Clone repository.
Run this command.

```
docker run -i -t --rm \
    -v /tmp/docker-python-telegram/:/tmp/ \
    -e API_ID=[id]
    -e API_HASH=[hash]
    -e PHONE=[phone] \
    -e PYTHONPATH=/app -v $PWD:/app \
    akhmetov/python-telegram python3 /app/tg/main.py
```

Where:

- `APP_ID` and `API_HASH` is keys from [telegram](https://core.telegram.org/api/obtaining_api_id)
- `PHONE` your phone number (or login)

If you don't want to run it using docker, install `tdlib` and `python-telegram`

For example, macOS:

```
brew install tdlib
pip3 install python-telegram
```


## Links

Usefull links to help develop this project.

- https://github.com/alexander-akhmetov/python-telegram
- https://github.com/tdlib/td/tree/master/example#python
