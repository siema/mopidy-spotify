from __future__ import unicode_literals

from mopidy_spotify import lookup, translator


def get_images(web_client, uris):
    result = {}
    for uri, item in lookup.web_lookups(web_client, uris).items():
        if translator.parse_uri(uri).type == 'track':
            result[uri] = tuple(translator.web_to_image(i)
                                for i in item['album']['images'])
        else:
            result[uri] = tuple(translator.web_to_image(i)
                                for i in item['images'])
    return result
