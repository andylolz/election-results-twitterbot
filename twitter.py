import os

import tweepy


class TwitterAPI:
    """
    Class for accessing the Twitter API.

    Requires API credentials to be available in environment
    variables. These will be set appropriately if the bot was created
    with init.sh included with the heroku-twitterbot-starter
    """
    def __init__(self):
        consumer_key = os.environ.get('TWITTER_CONSUMER_KEY')
        consumer_secret = os.environ.get('TWITTER_CONSUMER_SECRET')
        auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
        access_token = os.environ.get('TWITTER_ACCESS_TOKEN')
        access_token_secret = os.environ.get('TWITTER_ACCESS_TOKEN_SECRET')
        auth.set_access_token(access_token, access_token_secret)
        self.api = tweepy.API(auth)

    def ignore_errors(func):
        def func_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                print(e)
        return func_wrapper

    @ignore_errors
    def tweet(self, **kwargs):
        """Send a tweet"""
        if "filename" in kwargs:
            return self.api.update_with_media(**kwargs)
        else:
            return self.api.update_status(**kwargs)

    @ignore_errors
    def delete(self, id):
        return self.api.destroy_status(id)

    @ignore_errors
    def add_to_list(self, list_id, twitter_handle):
        return self.api.add_list_member(list_id=list_id, screen_name=twitter_handle)

    @ignore_errors
    def remove_from_list(self, list_id, twitter_handle):
        return self.api.remove_list_member(list_id=list_id, screen_name=twitter_handle)
