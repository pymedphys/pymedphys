import json
import os
import sys
import traceback
from glob import glob

import numpy as np
import pandas as pd

import requests
import win32com.client
import yaml

# Copyright (C) 2018 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


broken_link_record = r"C:\Users\sbiggs\last_broken_list.yml"
key_filepath = r"C:\Users\sbiggs\email-key.txt"


def send_email(subject, message):
    with open(key_filepath, "r") as keyfile:
        key = keyfile.read()

    return requests.post(
        "https://api.mailgun.net/v3/simonbiggs.net/messages",
        auth=("api", key),
        data={
            "from": "LinkCheckerBot <noreply@simonbiggs.net>",
            "to": ["sbiggs@riverinacancercare.com.au"],
            "subject": subject,
            "text": message,
        },
    )


def check_links():
    top_level = glob(r"S:\*.lnk")
    one_deep = glob(r"S:\*\*.lnk")
    two_deep = glob(r"S:\*\*\*.lnk")
    three_deep = glob(r"S:\*\*\*\*.lnk")
    all_paths = np.array(top_level + one_deep + two_deep + three_deep)

    shell = win32com.client.Dispatch("WScript.Shell")

    all_shorcuts = [shell.CreateShortCut(path) for path in all_paths]

    target_exists = np.array(
        [os.path.exists(shortcut.Targetpath) for shortcut in all_shorcuts]
    )

    current_broken = all_paths[np.invert(target_exists)].tolist()

    with open(broken_link_record, "r") as file:
        previous_broken = yaml.load(file)

    new_broken = np.setdiff1d(current_broken, previous_broken)

    if len(new_broken) > 0:
        message = (
            """New broken links:
        """
            + json.dumps(new_broken.tolist())
            + """

All broken links:
        """
            + json.dumps(current_broken)
        )
        send_email("New Links Broken", message)

    with open(broken_link_record, "w") as outfile:
        yaml.dump(current_broken, outfile)


try:
    check_links()
except Exception:
    send_email("Link Checker Had Error", "".join(traceback.format_exc()))
    raise
