"""Preserve every source pixel while padding thin strips for the local encoder."""
import struct

def png_for_vision(png):
    if not png.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('Expected captured PNG')
    width,height=struct.unpack('>II',png[16:24])
    if height>=64 and width<=12*height:return png
    import pymupdf
    source=pymupdf.Pixmap(png)
    if source.colorspace!=pymupdf.csRGB:source=pymupdf.Pixmap(pymupdf.csRGB,source)
    padded_height=max(128,height,(width+7)//8)
    target=pymupdf.Pixmap(pymupdf.csRGB,pymupdf.IRect(0,0,width,padded_height),False);target.clear_with(255)
    source.set_origin(0,(padded_height-height)//2);target.copy(source,source.irect)
    return target.tobytes('png')
