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


from pymedphys._imports import tensorflow as tf


def _bytes_feature(value):
    value = value.numpy()
    return tf.train.Feature(bytes_list=tf.train.BytesList(value=[value]))


def serialise(ct_uid, input_array, output_array):
    ct_uid = tf.io.serialize_tensor(ct_uid)
    input_array = tf.io.serialize_tensor(input_array)
    output_array = tf.io.serialize_tensor(output_array)

    feature = {
        "ct_uid": _bytes_feature(ct_uid),
        "input_array": _bytes_feature(input_array),
        "output_array": _bytes_feature(output_array),
    }

    example_proto = tf.train.Example(features=tf.train.Features(feature=feature))
    return example_proto.SerializeToString()


# Details on this from https://www.tensorflow.org/tutorials/load_data/tfrecord
def tf_serialise(ct_uid, input_array, output_array):
    tf_string = tf.py_function(
        serialise, (ct_uid, input_array, output_array), tf.string
    )
    return tf.reshape(tf_string, ())


def write_tfrecord(path,):

    writer = tf.data.experimental.TFRecordWriter(path)
    writer.write(serialised_dataset)
