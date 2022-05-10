
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

# pylint: disable=missing-docstring

from threading import Timer

from .logger import is_verbose, logger


class Spinner():

    def __init__(self, cmd, begin_msg="In Progress", end_msg=" ✓ Finished"):
        self._controller = cmd.cli_ctx.get_progress_controller()
        self.begin_msg, self.end_msg = begin_msg, end_msg
        self.tick()

    def begin(self, **kwargs):
        if not is_verbose():
            self._controller.begin(**kwargs)

    def end(self, **kwargs):
        self._controller.end(**kwargs)

    def tick(self):
        if not is_verbose() and self._controller.is_running():
            Timer(0.25, self.tick).start()
            self.update()

    def update(self):
        self._controller.update()

    def __enter__(self):
        self._controller.begin(message=self.begin_msg)
        logger.info(self.begin_msg)
        return self

    def __exit__(self, _type, value, traceback):
        if traceback:
            logger.debug(traceback)
            self._controller.end()
        else:
            self._controller.end(message=self.end_msg)
            logger.warning(self.end_msg)
