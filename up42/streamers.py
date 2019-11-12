# Standard libraries
import enum
import threading

# Third-party library
import loguru


class Progress(enum.Enum):
    PULLING = enum.auto()
    WAITING = enum.auto()
    DOWNLOADING = enum.auto()
    VERIFYING = enum.auto()
    DOWNLOAD_COMPLETED = enum.auto()
    EXTRACTING = enum.auto()
    PULL_COMPLETED = enum.auto()


class ImageBuildLogsThread(threading.Thread):

    def __init__(self, streamer):
        self._logs_streamer = streamer
        self._succeeded = False
        super(ImageBuildLogsThread, self).__init__(name='ImageBuildLogsThread')

    @property
    def succeeded(self):
        return self._succeeded

    def run(self):
        loguru.logger.info('Start image build logs streaming.')
        for log_line in self._logs_streamer:
            if 'stream' in log_line:
                line = log_line['stream'].replace('\n', '')
            elif 'errorDetail' in log_line:
                line = log_line['errorDetail']['message'].replace('\n', '')
            else:
                continue
            if line != '\n':
                loguru.logger.info(line)
            if 'Successfully built' in line:
                self._succeeded = True


class ImagePullLogsThread(threading.Thread):

    def __init__(self, streamer):
        self._logs_streamer = streamer
        self._layers_progress = {}
        super(ImagePullLogsThread, self).__init__(name='ImagePullLogsThread')

    def run(self):
        for log_line in self._logs_streamer:
            if 'status' in log_line:
                # Layer pulling
                if log_line['status'] == 'Pulling fs layer':
                    self._layers_progress[log_line['id']] = Progress.PULLING
                elif log_line['status'] == 'Waiting':
                    self._layers_progress[log_line['id']] = Progress.WAITING
                elif log_line['status'] == 'Downloading':
                    self._layers_progress[log_line['id']] = Progress.DOWNLOADING
                elif log_line['status'] == 'Verifying Checksum':
                    self._layers_progress[log_line['id']] = Progress.VERIFYING
                elif log_line['status'] == 'Download complete':
                    self._layers_progress[log_line['id']] = Progress.DOWNLOAD_COMPLETED
                elif log_line['status'] == 'Extracting':
                    self._layers_progress[log_line['id']] = Progress.EXTRACTING
                elif log_line['status'] == 'Pull complete':
                    self._layers_progress[log_line['id']] = Progress.PULL_COMPLETED
                    nb_layers = len(self._layers_progress.keys())
                    nb_layers_completed = len(list(filter(lambda progress: progress == Progress.PULL_COMPLETED,
                                                          self._layers_progress.values())))
                    loguru.logger.info('Pull of layer ({}) completed. Progress: {}/{}'.format(log_line['id'],
                                                                                              nb_layers_completed,
                                                                                              nb_layers))
                else:
                    loguru.logger.info(log_line['status'])
