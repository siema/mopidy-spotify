from __future__ import unicode_literals

import itertools
import logging
import operator

import spotify

from mopidy_spotify import translator, utils


logger = logging.getLogger(__name__)

_VARIOUS_ARTISTS_URIS = [
    'spotify:artist:0LyfQWJT6nXafLPZqxe9Of',
]

_API_MAX_IDS_PER_REQUEST = 50
_API_BASE_URI = 'https://api.spotify.com/v1/%ss/?ids=%s'

def lookup(config, session, uri):
    try:
        sp_link = session.get_link(uri)
    except ValueError as exc:
        logger.info('Failed to lookup "%s": %s', uri, exc)
        return []

    try:
        if sp_link.type is spotify.LinkType.TRACK:
            return list(_lookup_track(config, sp_link))
        elif sp_link.type is spotify.LinkType.ALBUM:
            return list(_lookup_album(config, sp_link))
        elif sp_link.type is spotify.LinkType.ARTIST:
            with utils.time_logger('Artist lookup'):
                return list(_lookup_artist(config, sp_link))
        elif sp_link.type is spotify.LinkType.PLAYLIST:
            return list(_lookup_playlist(config, sp_link))
        elif sp_link.type is spotify.LinkType.STARRED:
            return list(reversed(list(_lookup_playlist(config, sp_link))))
        else:
            logger.info(
                'Failed to lookup "%s": Cannot handle %r',
                uri, sp_link.type)
            return []
    except spotify.Error as exc:
        logger.info('Failed to lookup "%s": %s', uri, exc)
        return []


def web_lookups(web_client, uris):
    # TODO: Add caching of lookups.
    result = {}
    uri_type_getter = operator.attrgetter('type')
    uris = sorted((translator.parse_uri(u) for u in uris), key=uri_type_getter)

    for uri_type, group in itertools.groupby(uris, uri_type_getter):
        batch = []
        for link in group:
            batch.append(link)
            if len(batch) >= _API_MAX_IDS_PER_REQUEST:
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

    data = web_client.get(_API_BASE_URI % (uri_type, ','.join(ordered_ids)))
    for item in data.get(uri_type + 's', []):
        if item:
            result[ids_to_links[item['id']].uri] = item

    return result


def _lookup_track(config, sp_link):
    sp_track = sp_link.as_track()
    sp_track.load(config['timeout'])
    track = translator.to_track(sp_track, bitrate=config['bitrate'])
    if track is not None:
        yield track


def _lookup_album(config, sp_link):
    sp_album = sp_link.as_album()
    sp_album_browser = sp_album.browse()
    sp_album_browser.load(config['timeout'])
    for sp_track in sp_album_browser.tracks:
        track = translator.to_track(
            sp_track, bitrate=config['bitrate'])
        if track is not None:
            yield track


def _lookup_artist(config, sp_link):
    sp_artist = sp_link.as_artist()
    sp_artist_browser = sp_artist.browse(
        type=spotify.ArtistBrowserType.NO_TRACKS)
    sp_artist_browser.load(config['timeout'])

    # Get all album browsers we need first, so they can start retrieving
    # data in the background.
    sp_album_browsers = []
    for sp_album in sp_artist_browser.albums:
        sp_album.load(config['timeout'])
        if not sp_album.is_available:
            continue
        if sp_album.type is spotify.AlbumType.COMPILATION:
            continue
        if sp_album.artist.link.uri in _VARIOUS_ARTISTS_URIS:
            continue
        sp_album_browsers.append(sp_album.browse())

    for sp_album_browser in sp_album_browsers:
        sp_album_browser.load(config['timeout'])
        for sp_track in sp_album_browser.tracks:
            track = translator.to_track(
                sp_track, bitrate=config['bitrate'])
            if track is not None:
                yield track


def _lookup_playlist(config, sp_link):
    sp_playlist = sp_link.as_playlist()
    sp_playlist.load(config['timeout'])
    for sp_track in sp_playlist.tracks:
        sp_track.load(config['timeout'])
        track = translator.to_track(
            sp_track, bitrate=config['bitrate'])
        if track is not None:
            yield track
