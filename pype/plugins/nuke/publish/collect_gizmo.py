import pyblish.api
import pype.api as pype
import nuke


@pyblish.api.log
class CollectGizmo(pyblish.api.InstancePlugin):
    """Collect Gizmo (group) node instance and its content
    """

    order = pyblish.api.CollectorOrder + 0.22
    label = "Collect Gizmo (Group)"
    hosts = ["nuke"]
    families = ["gizmo"]

    def process(self, instance):

        grpn = instance[0]

        # add family to familiess
        instance.data["families"].insert(0, instance.data["family"])
        # make label nicer
        instance.data["label"] = "{0} ({1} nodes)".format(
            grpn.name(), len(instance) - 1)

        # Get frame range
        handle_start = instance.context.data["handleStart"]
        handle_end = instance.context.data["handleEnd"]
        first_frame = int(nuke.root()["first_frame"].getValue())
        last_frame = int(nuke.root()["last_frame"].getValue())

        # get version
        version = pype.get_version_from_path(nuke.root().name())
        instance.data['version'] = version

        # Add version data to instance
        version_data = {
            "handles": handle_start,
            "handleStart": handle_start,
            "handleEnd": handle_end,
            "frameStart": first_frame + handle_start,
            "frameEnd": last_frame - handle_end,
            "colorspace": nuke.root().knob('workingSpaceLUT').value(),
            "version": int(version),
            "families": [instance.data["family"]] + instance.data["families"],
            "subset": instance.data["subset"],
            "fps": instance.context.data["fps"]
        }

        instance.data.update({
            "versionData": version_data,
            "frameStart": first_frame,
            "frameEnd": last_frame
        })
        self.log.info("Gizmo content collected: `{}`".format(instance[:]))
        self.log.info("Gizmo instance collected: `{}`".format(instance))
