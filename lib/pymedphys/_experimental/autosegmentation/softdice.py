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


from pymedphys._imports import numpy as np
from pymedphys._imports import skimage


def soft_surface_dice(reference, evaluation):
    """Non-TensorFlow implementation of a soft surface dice"""
    edge_reference = skimage.filters.scharr(reference)
    edge_evaluation = skimage.filters.scharr(evaluation)

    score = np.sum(np.abs(edge_evaluation - edge_reference)) / np.sum(
        edge_evaluation + edge_reference
    )

    return 1 - score


def tf_soft_surface_dice(reference, evaluation):
    """TensorFlow implementation of a soft surface dice"""
    raise NotImplementedError()
