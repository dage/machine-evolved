# Removes unused models from the disk to avoid ever increasing disk usage
#
# To get around the problem of growing and not-deletable events.out.tfevents files, 
# comment out the `self._ev_writer.WriteEvent(event)` statement in `Anaconda3\envs\tensorflow\Lib\site-packages\tensorflow\python\summary\event_file_writer.py`.

import shutil
import os
import stat

class DiskCleaner:
    def __init__(self):
        self.queue = []

    def mark_for_delete(self, path):
        self.queue.append(path)

    def clean(self, print_stats = True):
        success_count = 0
        failed_queue = []
        last_error = ""

        freed_disk_space = 0
        for path in self.queue:
            disk_space = 0
            for item in os.scandir(path):
                if item.is_file():
                    disk_space += item.stat().st_size

            try:
                shutil.rmtree(path) #     ignore_errors=True
                success = True
            except Exception as e:
                success = False

                last_error = "{}".format(e)

            if success:
                success_count += 1
                freed_disk_space += disk_space
            else:
                failed_queue.append(path)

        if print_stats:
            print("{} model directories deleted, freeing {:.2f}MB. {} failed. {}".format(success_count, freed_disk_space/1000/1000, len(failed_queue), last_error))

        self.queue = failed_queue