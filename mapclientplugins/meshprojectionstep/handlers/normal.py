"""
Created: January, 2024

@author: tsalemink
"""
import numpy as np

from cmlibs.widgets.handlers.keyactivatedhandler import KeyActivatedHandler
from cmlibs.widgets.errors import HandlerError
from cmlibs.maths.vectorops import sub, mult, dot
from cmlibs.maths.algorithms import calculate_centroid
from cmlibs.utils.zinc.scene import create_plane_normal_indicator, get_glyph_position, set_glyph_position
from cmlibs.utils.zinc.node import translate_nodes


NORMAL_ARROW_SIZE = 25.0


class Normal(KeyActivatedHandler):

    def __init__(self, key_code):
        super().__init__(key_code)

        self._model = None

        # Two glyphs for each of the three translation axes (x, y, normal).
        self._glyphs = []
        self._reverse_glyphs = []
        self._glyph_fields = []

        self._default_material = None
        self._selected_material = None
        self._start_position = None
        self._selected_index = None

    def set_model(self, model):
        attributes = ['get_projection_plane_region', 'set_rotation_point', 'get_plane_normal', 'plane_nodes_coordinates']

        if all(hasattr(model, attr) for attr in attributes):
            self._model = model

            self._glyphs = []
            self._reverse_glyphs = []
            self._glyph_fields = []

            region = model.get_projection_plane_region()
            field_module = region.getFieldmodule()
            scene = region.getScene()
            self._glyph_fields.append(field_module.createFieldConstant([0, 0, 0]))
            self._glyph_fields.append(field_module.createFieldConstant([0, 0, 0]))
            self._glyph_fields.append(field_module.createFieldConstant([0, 0, 0]))
            self._glyphs.append(create_plane_normal_indicator(scene, self._glyph_fields[0], size=NORMAL_ARROW_SIZE))
            self._glyphs.append(create_plane_normal_indicator(scene, self._glyph_fields[1], size=NORMAL_ARROW_SIZE))
            self._glyphs.append(create_plane_normal_indicator(scene, self._glyph_fields[2], size=NORMAL_ARROW_SIZE))
            self._reverse_glyphs.append(create_plane_normal_indicator(scene, self._glyph_fields[0], size=-NORMAL_ARROW_SIZE))
            self._reverse_glyphs.append(create_plane_normal_indicator(scene, self._glyph_fields[1], size=-NORMAL_ARROW_SIZE))
            self._reverse_glyphs.append(create_plane_normal_indicator(scene, self._glyph_fields[2], size=-NORMAL_ARROW_SIZE))

            self._initialise_materials()

        else:
            raise HandlerError('Given model does not have the required API for handling translation.')

    def _initialise_materials(self):
        context = self._model.get_projection_plane_region().getContext()
        material_module = context.getMaterialmodule()
        self._default_material = material_module.findMaterialByName('orange')
        self._selected_material = material_module.findMaterialByName('red')

    def enter(self):
        x_vector, y_vector = calculate_orthogonal_vectors(self._model.plane_nodes_coordinates())
        normal = self._model.get_plane_normal()

        x_field_cache = self._glyph_fields[0].getFieldmodule().createFieldcache()
        y_field_cache = self._glyph_fields[1].getFieldmodule().createFieldcache()
        normal_field_cache = self._glyph_fields[2].getFieldmodule().createFieldcache()
        self._glyph_fields[0].assignReal(x_field_cache, x_vector.tolist())
        self._glyph_fields[1].assignReal(y_field_cache, y_vector.tolist())
        self._glyph_fields[2].assignReal(normal_field_cache, normal)

        centroid = calculate_centroid(self._model.plane_nodes_coordinates()).tolist()
        for glyph in (self._glyphs + self._reverse_glyphs):
            glyph.setVisibilityFlag(True)
            glyph.setMaterial(self._default_material)
            set_glyph_position(glyph, centroid)

    def leave(self):
        for glyph in (self._glyphs + self._reverse_glyphs):
            glyph.setVisibilityFlag(False)

        self._start_position = None
        self._selected_index = None

    def mouse_press_event(self, event):
        super().mouse_press_event(event)

        pixel_scale = self._scene_viewer.get_pixel_scale()
        x, y = event.x() * pixel_scale, event.y() * pixel_scale
        self._start_position = [x, y]

        graphic = self._scene_viewer.get_nearest_graphics_point(x, y)
        if graphic and graphic.isValid():
            for i in range(len(self._glyphs)):
                if graphic == self._glyphs[i] or graphic == self._reverse_glyphs[i]:
                    self._selected_index = i
                    self._glyphs[i].setMaterial(self._selected_material)
                    self._reverse_glyphs[i].setMaterial(self._selected_material)

    def mouse_move_event(self, event):
        if self._selected_index is not None:
            pixel_scale = self._scene_viewer.get_pixel_scale()
            x = event.x() * pixel_scale
            y = event.y() * pixel_scale
            pos = get_glyph_position(self._glyphs[2])
            screen_pos = self._scene_viewer.project(pos[0], pos[1], pos[2])
            global_cur_pos = self._scene_viewer.unproject(x, -y, screen_pos[2])
            global_old_pos = self._scene_viewer.unproject(self._start_position[0], -self._start_position[1], screen_pos[2])
            global_pos_diff = sub(global_cur_pos, global_old_pos)

            field_cache = self._glyph_fields[self._selected_index].getFieldmodule().createFieldcache()
            _, vector = self._glyph_fields[self._selected_index].evaluateReal(field_cache, 3)
            proj_n = mult(vector, dot(global_pos_diff, vector))

            scene = self._glyphs[2].getScene()
            scene.beginChange()

            translate_nodes(self._model.get_projection_plane_region(), proj_n)
            centroid = calculate_centroid(self._model.plane_nodes_coordinates()).tolist()
            if centroid is not None:
                self._model.set_rotation_point(centroid)
                for glyph in (self._glyphs + self._reverse_glyphs):
                    set_glyph_position(glyph, centroid)

            scene.endChange()
            self._start_position = [x, y]
        else:
            super(Normal, self).mouse_move_event(event)

    def mouse_release_event(self, event):
        super().mouse_release_event(event)

        for glyph in (self._glyphs + self._reverse_glyphs):
            glyph.setMaterial(self._default_material)

        self._start_position = None
        self._selected_index = None


def calculate_orthogonal_vectors(points):
    vectors = [np.array(point) - points[0] for point in points[1:]]
    lengths = [np.linalg.norm(vector) for vector in vectors]
    max_index = int(np.argmax(lengths))
    vectors.pop(max_index)
    lengths.pop(max_index)

    return (vectors[0] / lengths[0]), (vectors[1] / lengths[1])
