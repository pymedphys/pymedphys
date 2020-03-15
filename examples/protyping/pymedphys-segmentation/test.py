import config
import data_generator
import model
import paths

input_paths, context_paths, label_paths = paths.get_paths(
    config.DATA_PATH, config.CONTEXT
)

train_paths, valid_paths, test_paths = paths.split_paths(input_paths, config.RATIO)

train_gen = data_generator.data_gen(
    train_paths,
    context_paths,
    label_paths,
    context=config.CONTEXT,
    batch_size=config.BATCH_SIZE,
    structure_names=config.STRUCTURE_NAMES,
    resize=config.GRID_SIZE,
)

valid_gen = data_generator.data_gen(
    valid_paths,
    context_paths,
    label_paths,
    context=config.CONTEXT,
    batch_size=config.BATCH_SIZE,
    structure_names=config.STRUCTURE_NAMES,
    resize=config.GRID_SIZE,
)

test_gen = data_generator.data_gen(
    test_paths,
    context_paths,
    label_paths,
    context=config.CONTEXT,
    batch_size=config.BATCH_SIZE,
    structure_names=config.STRUCTURE_NAMES,
    resize=config.GRID_SIZE,
)

test_gen.plot_instance()
