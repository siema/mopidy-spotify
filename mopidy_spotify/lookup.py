from __future__ import unicode_literals

import itertools
import logging
import operator

from mopidy_spotify import translator, utils


logger = logging.getLogger(__name__)

_VARIOUS_ARTISTS_URIS = [
    'spotify:artist:0LyfQWJT6nXafLPZqxe9Of',
]

_API_MAX_IDS_PER_REQUEST = 50
_API_BASE_LOOKUP_URI = 'https://api.spotify.com/v1/%ss/?ids=%s'


def lookup(config, session, web_client, uri):
    try:
        web_link = translator.parse_uri(uri)
    except ValueError as exc:
        logger.info('Failed to lookup "%s": %s', uri, exc)
        return []

    if web_link.type == 'track':
        return list(_lookup_track(web_client, config, web_link))
    elif web_link.type == 'album':
        return list(_lookup_album(web_client, config, web_link))
    elif web_link.type == 'artist':
        with utils.time_logger('Artist lookup'):
            return list(_lookup_artist(web_client, config, web_link))
    elif web_link.type == 'playlist':
        return list(_lookup_playlist(web_client, config, web_link))
    elif web_link.type == 'starred':
        return list(reversed(_lookup_starred(web_client, config, web_link)))

    logger.info('Failed to lookup "%s".', uri)
    return []


def web_lookup(web_client, uri):
    return web_lookups(web_client, [uri]).get(uri)


def web_lookups(web_client, uris, limit=None):
    # TODO: Add caching of lookups.
    # TODO: Check for errors and handle them.
    # TODO: Add specific tests for web_lookups.
    result = {}
    uri_type_getter = operator.attrgetter('type')
    uris = sorted((translator.parse_uri(u) for u in uris), key=uri_type_getter)

    for uri_type, group in itertools.groupby(uris, uri_type_getter):
        batch = []
        for link in group:
            batch.append(link)
            if len(batch) >= (limit or _API_MAX_IDS_PER_REQUEST):
                result.update(
                    _process_web_lookups_batch(web_client, uri_type, batch))
                batch = []
        result.update(_process_web_lookups_batch(web_client, uri_type, batch))
    return result


def _process_web_lookups_batch(web_client, uri_type, batch):
    result = {}
    ordered_ids = [l.id for l in batch]
    ids_to_links = {l.id: l for l in batch}

    if not batch:
        return result

    data = web_client.get(
        _API_BASE_LOOKUP_URI % (uri_type, ','.join(ordered_ids)))
    for item in data.get(uri_type + 's', []):
        if item:
            result[ids_to_links[item['id']].uri] = item

    return result


def _lookup_track(web_client, config, link):
    yield translator.web_to_track(
        web_lookup(web_client, link.uri), bitrate=config['bitrate'])


def _lookup_album(web_client, config, link):
    return _convert_album(web_lookup(web_client, link.uri), config)


def _convert_album(result, config):
    album = translator.web_to_album(result)
    # TODO: Check for result next pagination.
    for item in result['tracks']['items']:
        yield translator.web_to_track(
            item, album=album, bitrate=config['bitrate'])


def _lookup_artist(web_client, config, link):
    artist_result = web_client.get(
        'https://api.spotify.com/v1/artists/%s/albums?'
        'album_type=album,single&limit=50' % link.id)
    # TODO: Limit to given country?
    # TODO: Check for result next pagination.
    album_uris = [i['uri'] for i in artist_result['items']]
    album_result = web_lookups(web_client, album_uris, limit=20)

    for album_uri in album_uris:
        for track in _convert_album(album_result[album_uri], config):
            yield track

    # TODO: Convert to using top tracks for artist?


def _lookup_playlist(web_client, config, link):
    # TODO: Check for result next pagination.
    result = web_client.get('https://api.spotify.com/v1/users/%s/playlists/%s/'
                            'tracks?limit=100&market=from_token' %
                            (link.id, link.owner))

    for item in result['items']:
        yield translator.web_to_track(item, bitrate=config['bitrate'])


def _lookup_starred(web_client, config, link):
    # TODO: Check for result next pagination.
    playlists_result = web_client.get(
        'https://api.spotify.com/v1/users/%s/playlists?limit=50' % link.owner)
    for playlist in playlists_result['items']:
        if playlist['name'] == 'Starred':
            link = translator.parse_uri(playlist['uri'])
            return list(_lookup_playlist(web_client, config, link))
    return []
