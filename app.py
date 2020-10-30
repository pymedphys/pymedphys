# Copyright (C) 2020 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""This is a streamlit app. To run this on your machine first install
the requirements:

    pip install -r requirements.txt

Then you can start this app by running:

    streamlit run app.py
"""


from pymedphys._gui.streamlit import index


def run():
    index.run()


if __name__ == "__main__":
    run()
