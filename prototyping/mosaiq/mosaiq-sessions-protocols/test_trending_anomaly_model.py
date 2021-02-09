import unittest
import tensorflow as tf
import numpy as np
import random


rng = np.random.default_rng()
num_samples = 100000
systematic_cov = np.identity(3) * 2.0
systematic_offsets = rng.multivariate_normal(np.zeros(3), systematic_cov, num_samples)
systematic_offsets


session_cov, session_count = np.identity(3) * 1.5, 5
samples, labels = [], []
for systematic_offset in systematic_offsets:
    mean_session_offset = np.mean(
        rng.multivariate_normal(systematic_offset, session_cov, session_count), 0
    )
    if random.randint(1, 10) <= 5:
        labels.append(0.0)
        systematic_offset = np.zeros(3)
    else:
        labels.append(1.0)
    samples.append(
        np.concatenate([[session_count], mean_session_offset, systematic_offset])
    )
samples = np.array(samples)
labels = np.array(labels)
print(samples)
print(labels)


ds = tf.data.Dataset.from_tensor_slices((samples, labels))
print(ds.element_spec)
for sample, label in ds.take(10):
    print(sample)
    print(label)


model = tf.keras.Sequential()
model.add(tf.keras.layers.Input(shape=(7,)))
model.add(tf.keras.layers.Dense(5, activation="relu"))
model.add(tf.keras.layers.Dense(1, activation="softmax"))
model.summary()


adam = tf.optimizers.Adam()  # lr=0.001, decay=1e-8)
model.compile(loss="binary_crossentropy", optimizer=adam)


ds_batch = ds.batch(32)
model.fit(ds_batch, epochs=10)


def create_fake_database():
    # sql to create the database

    # use pandas to create dataframes for Site, Dose_Hst, and Offset

    # write the dataframes to the db

    pass


class TestTrendingDataset(unittest.UnitTest):
    def __init__(self):
        pass

    def test_clustering(self):
        test_dttms = [datetime.now() + timedelta(hours=h) for h in range(10)]
        list(cluster_sessions(test_dttms))

    def test_sessions_for_site(self):
        pass

    def test_session_offsets_for_site(self):
        pass

    def test_generate_labeled(self):
        pass

    def test_train(self):
        pass


if __name__ == "__main__":
    unittest.run()
