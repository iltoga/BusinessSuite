import base64
import json

import requests


def refresh_dropbox_token(app_key, app_secret, refresh_token):
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    headers = {
        "Authorization": "Basic "
        + base64.b64encode(f"{app_key}:{app_secret}".encode()).decode(),  # Replace with your app key and secret
        "Content-Type": "application/x-www-form-urlencoded",
    }
    response = requests.post("https://api.dropboxapi.com/oauth2/token", headers=headers, data=data, timeout=10)

    response.raise_for_status()  # This will raise an HTTPError if the request failed

    # the response JSON is in the text attribute and have to decode it
    text = response.text
    json_response = json.loads(text)
    if "access_token" in json_response:
        return json_response["access_token"]
    else:
        raise KeyError("access_token not found in the response. Response was: {}".format(json_response))
