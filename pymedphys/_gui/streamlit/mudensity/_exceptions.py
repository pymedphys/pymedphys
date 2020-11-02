# Copyright (C) 2020 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from pymedphys._streamlit.exceptions import (  # pylint: disable=unused-import
    NoRecordsFound,
)


class InputRequired(ValueError):
    pass


class WrongFileType(ValueError):
    pass


class UnableToCreatePDF(ValueError):
    pass


class NoControlPointsFound(ValueError):
    pass


class NoMosaiqAccess(ValueError):
    pass


class ConfigMissing(ValueError):
    pass
