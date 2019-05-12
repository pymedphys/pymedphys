import os
import shutil


def save_dot_file(dot_contents, outfilepath):
    with open("temp.dot", 'w') as file:
        file.write(dot_contents)

    os.system("cat temp.dot | tred | dot -Tsvg -o temp.svg")
    os.remove("temp.dot")
    # shutil.move("temp.dot", outfilepath + ".dot")

    shutil.move("temp.svg", outfilepath)


def remove_prefix(text, prefix):
    if text.startswith(prefix):
        return text[len(prefix):]
    else:
        return text