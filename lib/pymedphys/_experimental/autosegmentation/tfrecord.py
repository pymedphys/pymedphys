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


from pymedphys._imports.slow import tensorflow as tf


def _bytes_feature(value):
    value = value.numpy()
    return tf.train.Feature(bytes_list=tf.train.BytesList(value=[value]))


def serialise(ct_uid, x_grid, y_grid, input_array, output_array):
    ct_uid = tf.io.serialize_tensor(ct_uid)
    x_grid = tf.io.serialize_tensor(x_grid)
    y_grid = tf.io.serialize_tensor(y_grid)
    input_array = tf.io.serialize_tensor(input_array)
    output_array = tf.io.serialize_tensor(output_array)

    feature = {
        "ct_uid": _bytes_feature(ct_uid),
        "x_grid": _bytes_feature(x_grid),
        "y_grid": _bytes_feature(y_grid),
        "input_array": _bytes_feature(input_array),
        "output_array": _bytes_feature(output_array),
    }

    example_proto = tf.train.Example(features=tf.train.Features(feature=feature))
    return example_proto.SerializeToString()


# Details on this from https://www.tensorflow.org/tutorials/load_data/tfrecord
def tf_serialise(ct_uid, x_grid, y_grid, input_array, output_array):
    tf_string = tf.py_function(
        serialise, (ct_uid, x_grid, y_grid, input_array, output_array), tf.string
    )
    return tf.reshape(tf_string, ())


def dump(dataset, path):
    serialised_dataset = dataset.map(tf_serialise)
    writer = tf.data.experimental.TFRecordWriter(path)
    writer.write(serialised_dataset)


def load(path):
    parse_features = {
        "ct_uid": tf.io.FixedLenFeature([], tf.string),
        "x_grid": tf.io.FixedLenFeature([], tf.string),
        "y_grid": tf.io.FixedLenFeature([], tf.string),
        "input_array": tf.io.FixedLenFeature([], tf.string),
        "output_array": tf.io.FixedLenFeature([], tf.string),
    }

    def _parse_dataset(example_proto):
        parsed = tf.io.parse_single_example(example_proto, parse_features)
        ct_uid = tf.io.parse_tensor(parsed["ct_uid"], tf.string)
        x_grid = tf.io.parse_tensor(parsed["x_grid"], tf.float64)
        y_grid = tf.io.parse_tensor(parsed["y_grid"], tf.float64)
        input_array = tf.io.parse_tensor(parsed["input_array"], tf.int32)
        output_array = tf.io.parse_tensor(parsed["output_array"], tf.float64)

        return ct_uid, x_grid, y_grid, input_array, output_array

    raw_dataset = tf.data.TFRecordDataset(path)
    parsed_dataset = raw_dataset.map(_parse_dataset)

    return parsed_dataset
