# Mackerel

A Python script which finds the longest journeys (by number of stops) in the London Underground, none of whose stops contain the letters of a given word or phrase.

I'm not sure why either.

# Usage

```
usage: mackerel.py [-h] [-e ENV] [--no-create-cache] [--force] [--cache-path CACHE_PATH] word

positional arguments:
  word                  Word to find longest tube journey for

options:
  -h, --help            show this help message and exit
  -e ENV, --env ENV     Environment to load
  --no-create-cache     Do not create a cached file of the tube data
  --force               Do not use the cached file of the tube data, even if it exists
  --cache-path CACHE_PATH
                        Path to the cached file of the tube data
```

## Example

```
$ python mackerel.py "aeo"

Longest tube journeys (in terms of number of stops) avoiding all letters in "aeo":
Found 2 journeys of length 3:

Kilburn
  |
  Jubilee
  ↓
Kingsbury
  |
  Jubilee
  ↓
Kilburn

--------------------

Kingsbury
  |
  Jubilee
  ↓
Kilburn
  |
  Jubilee
  ↓
Kingsbury

--------------------


Found 5 stations without these letters:

Buckhurst Hill
Kilburn
Kingsbury
Ruislip
Sudbury Hill
```