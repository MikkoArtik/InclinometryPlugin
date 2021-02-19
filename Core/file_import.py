import numpy as np


def load_points_file(file_path):
    data = []
    with open(file_path) as f:
        headers = f.readline().rstrip().split('\t')
        for line in f:
            data.append(line.rstrip().split('\t'))
    return headers, data


def load_incl_file(file_path):
    with open(file_path, 'r') as f:
        file_columns = f.readline().rstrip().split('\t')

    file_data = np.loadtxt(file_path, skiprows=1, delimiter='\t')
    return file_columns, file_data
