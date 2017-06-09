from __future__ import unicode_literals

import itertools
import logging
import operator

from mopidy_spotify import translator


# NOTE: This module is independent of libspotify and built using the Spotify
# Web APIs. As such it does not tie in with any of the regular code used
# elsewhere in the mopidy-spotify extensions. It is also intended to be used
# across both the 1.x and 2.x versions.

_API_MAX_IDS_PER_REQUEST = 50
_API_BASE_URI = 'https://api.spotify.com/v1/%ss/?ids=%s'

_cache = {}  # (type, id) -> [Image(), ...]

logger = logging.getLogger(__name__)


def get_images(web_client, uris):
    result = {}
    uri_type_getter = operator.attrgetter('type')
    uris = sorted((translator.parse_uri(u) for u in uris), key=uri_type_getter)
    for uri_type, group in itertools.groupby(uris, uri_type_getter):
        batch = []
        for link in group:
            key = (link.type, link.id)
            if key in _cache:
                result[link.uri] = _cache[key]
            else:
                batch.append(link)
                if len(batch) >= _API_MAX_IDS_PER_REQUEST:
                    result.update(
                        _process_uris(web_client, uri_type, batch))
                    batch = []
        result.update(_process_uris(web_client, uri_type, batch))
    return result


def _process_uris(web_client, uri_type, links):
    result = {}
    ordered_ids = [l.id for l in links]
    ids_to_links = {l.id: l for l in links}

    if not links:
        return result

    lookup_uri = _API_BASE_URI % (uri_type, ','.join(ordered_ids))

    data = web_client.get(lookup_uri)

    for item in data.get(uri_type + 's', []):
        if not item:
            continue
        link = ids_to_links[item['id']]
        key = (link.type, link.id)
        if key not in _cache:
            if uri_type == 'track':
                album_link = translator.parse_uri(item['album']['uri'])
                album_key = (album_link.type, album_link.id)
                if album_key not in _cache:
                    _cache[album_key] = tuple(translator.web_to_image(i)
                                              for i in item['album']['images'])
                _cache[key] = _cache[album_key]
            else:
                _cache[key] = tuple(translator.web_to_image(i)
                                    for i in item['images'])
        result[link.uri] = _cache[key]

    return result
