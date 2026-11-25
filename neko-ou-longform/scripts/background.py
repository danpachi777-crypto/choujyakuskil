"""The landscape layout for a moving secondary picture behind the story and captions."""

ART_BOX = (62, 130, 1048, 590)
FOOTAGE_BOX = (1150, 132, 724, 664)


def footage_filter(stream, focus=0.5, fit="cover"):
    """Crop the secondary picture in its own panel without changing the main picture."""
    _, _, width, height = FOOTAGE_BOX
    if fit=='contain':
        sizing=(f'scale={width}:{height}:force_original_aspect_ratio=decrease,'
                f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x0e182a')
    else:
        sizing=(f'scale={width}:{height}:force_original_aspect_ratio=increase,'
                f'crop={width}:{height}:(iw-ow)*{focus:.4f}:(ih-oh)*0.5')
    return f'[{stream}:v]fps=30,{sizing},setsar=1,format=yuv420p[footage]'


def footage_inputs(path, position, duration):
    # The start of each subtitle resumes the same continuous background timeline.
    return ['-stream_loop','-1','-ss',str(position % duration),'-i',str(path)]
