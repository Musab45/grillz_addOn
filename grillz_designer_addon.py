# blender_grillz_addon.py

# Tell Blender this is an Add-on
bl_info = {
    "name": "Grillz Designer",
    "author": "AI Assistant & You",
    "version": (0, 5, 0),
    "blender": (2, 80, 0),
    "location": "View3D > Sidebar > Grillz Designer",
    "description": "A non-destructive tool to assist in the design of custom grillz from 3D dental scans.",
    "category": "3D View",
}

import bpy
import bmesh

# -------------------------------------------------------------------
# OPERATOR: The action that performs the grill generation
# -------------------------------------------------------------------
class GRILLZ_OT_GenerateGrill(bpy.types.Operator):
    """Creates a new object from the selected teeth and builds a grill without modifying the original scan."""
    bl_idname = "grillz.generate_base"
    bl_label = "Generate Grill From Selection"
    bl_options = {'REGISTER', 'UNDO'}

    # --- Properties for the operator (will appear in the pop-up/UI) ---
    thickness: bpy.props.FloatProperty(
        name="Thickness (mm)",
        description="How thick the grill will be",
        default=0.6, min=0.2, max=5.0, unit='LENGTH'
    )

    remesh_voxel_size: bpy.props.FloatProperty(
        name="Detail Level (Voxel Size)",
        description="Lower values mean more detail, but more polygons. 0.1 is a good start.",
        default=0.1, min=0.01, max=1.0, unit='LENGTH'
    )
    
    decimate_ratio: bpy.props.FloatProperty(
        name="Poly-Count Reduction",
        description="Reduces final polygon count. 1.0 is no change, 0.5 is 50% reduction.",
        default=0.5, min=0.05, max=1.0
    )
    
    # --- The main execution function ---
    def execute(self, context):
        # 1. --- VALIDATION ---
        # Ensure we are in Edit Mode on a valid mesh object
        if context.mode != 'EDIT_MESH':
            self.report({'WARNING'}, "Please switch to Edit Mode to select teeth.")
            return {'CANCELLED'}
            
        source_obj = context.edit_object
        if source_obj is None or source_obj.type != 'MESH':
            self.report({'WARNING'}, "An editable mesh object must be active.")
            return {'CANCELLED'}

        # 2. --- NON-DESTRUCTIVE GEOMETRY COPY (using BMesh) ---
        # This is the safe way to create the grill base. It builds a new
        # mesh instead of duplicating and separating from the original.
        
        # Get the bmesh representation of the edit-mode mesh
        bm = bmesh.from_edit_mesh(source_obj.data)
        
        # Check for selection
        if not any(v.select for v in bm.verts):
            self.report({'WARNING'}, "You must select the teeth vertices first.")
            return {'CANCELLED'}

        # Create a new mesh data-block for our grill object
        new_mesh = bpy.data.meshes.new("Grill_Base_Mesh")
        
        # Create a BMesh for the new mesh
        new_bm = bmesh.new()

        # Create a mapping from old vertices to new vertices to preserve connections
        vert_map = {}

        # Copy selected faces and their vertices to the new BMesh
        for face in bm.faces:
            if face.select:
                new_verts = []
                for vert in face.verts:
                    # If we haven't copied this vertex yet, copy it now
                    if vert not in vert_map:
                        new_v = new_bm.verts.new(vert.co)
                        vert_map[vert] = new_v
                    new_verts.append(vert_map[vert])
                # Create the new face with the copied vertices
                new_bm.faces.new(new_verts)
        
        # If no faces were selected (only verts or edges), copy just the verts
        if not new_bm.faces:
             for vert in bm.verts:
                 if vert.select:
                     new_bm.verts.new(vert.co)

        # Write the new BMesh data into our new mesh
        new_bm.to_mesh(new_mesh)
        new_bm.free()

        # Create the new object and link it to the scene
        grill_object = bpy.data.objects.new("Grill_Base", new_mesh)
        context.collection.objects.link(grill_object)
        
        # 3. --- PREPARE THE NEW OBJECT ---
        # Deselect all objects and select our new grill object to make it active
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        grill_object.select_set(True)
        context.view_layer.objects.active = grill_object

        # 4. --- FIX THE ORIGIN ---
        bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')

        # 5. --- ADD ROBUST MODIFIER STACK ---
        # --- WELD MODIFIER (Step 1: Clean) ---
        weld_mod = grill_object.modifiers.new(name="Grill_Weld", type='WELD')
        weld_mod.merge_threshold = 0.01

        # --- SOLIDIFY MODIFIER (Step 2: Thicken) ---
        solidify_mod = grill_object.modifiers.new(name="Grill_Thickness", type='SOLIDIFY')
        solidify_mod.thickness = self.thickness
        solidify_mod.offset = 1
        # Removed the 'solidify_mode' line that was causing a crash.

        # --- REMESH MODIFIER (Step 3: Rebuild) ---
        remesh_mod = grill_object.modifiers.new(name="Grill_Remesh", type='REMESH')
        remesh_mod.mode = 'VOXEL'
        remesh_mod.voxel_size = self.remesh_voxel_size
        remesh_mod.use_remove_disconnected = True

        # --- LAPLACIAN SMOOTH MODIFIER (Step 4: Refine Shape - FIX) ---
        # Replaced CorrectiveSmooth with LaplacianSmooth to fix vertex count error and improve smoothing.
        lap_smooth_mod = grill_object.modifiers.new(name="Grill_LaplacianSmooth", type='LAPLACIANSMOOTH')
        lap_smooth_mod.iterations = 5
        lap_smooth_mod.use_volume_preserve = True # Prevents shrinking

        # --- DECIMATE MODIFIER (Step 5: Optimize Polycount) ---
        decimate_mod = grill_object.modifiers.new(name="Grill_Decimate", type='DECIMATE')
        decimate_mod.ratio = self.decimate_ratio

        self.report({'INFO'}, "Non-destructively generated Grill_Base object.")
        return {'FINISHED'}


# -------------------------------------------------------------------
# UI PANEL: The interface in the 3D View Sidebar
# -------------------------------------------------------------------
class GRILLZ_PT_MainPanel(bpy.types.Panel):
    """Creates a Panel in the 3D View Sidebar"""
    bl_label = "Grillz Designer"
    bl_idname = "GRILLZ_PT_MainPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Grillz Designer'

    def draw(self, context):
        layout = self.layout
        
        box = layout.box()
        box.label(text="Instructions:", icon='INFO')
        col = box.column(align=True)
        col.label(text="1. Import your dental scan (STL/OBJ).")
        col.label(text="2. Select the scan object.")
        col.label(text="3. Switch to Edit Mode (Tab key).")
        col.label(text="4. Select the teeth for the grill.")
        col.label(text="5. Click 'Generate Grill' below.")

        layout.separator()

        gen_box = layout.box()
        gen_box.label(text="Phase 1: Generate Base", icon='MOD_SOLIDIFY')
        
        col = gen_box.column()
        col.prop(context.scene, "grillz_thickness")
        col.prop(context.scene, "grillz_remesh_voxel_size")
        col.prop(context.scene, "grillz_decimate_ratio")
        
        op = col.operator(GRILLZ_OT_GenerateGrill.bl_idname, icon='AUTO')
        op.thickness = context.scene.grillz_thickness
        op.remesh_voxel_size = context.scene.grillz_remesh_voxel_size
        op.decimate_ratio = context.scene.grillz_decimate_ratio


# -------------------------------------------------------------------
# REGISTRATION: To add/remove the add-on from Blender
# -------------------------------------------------------------------
classes = (
    GRILLZ_OT_GenerateGrill,
    GRILLZ_PT_MainPanel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
        
    bpy.types.Scene.grillz_thickness = bpy.props.FloatProperty(
        name="Thickness (mm)",
        description="How thick the grill will be",
        default=0.6, min=0.2, max=5.0, unit='LENGTH'
    )
    bpy.types.Scene.grillz_remesh_voxel_size = bpy.props.FloatProperty(
        name="Detail Level (Voxel Size)",
        description="Lower values mean more detail. 0.1 is a good start.",
        default=0.1, min=0.01, max=1.0, unit='LENGTH'
    )
    bpy.types.Scene.grillz_decimate_ratio = bpy.props.FloatProperty(
        name="Poly-Count Reduction",
        description="Reduces final polygon count. 1.0 is no change, 0.5 is 50% reduction.",
        default=0.5, min=0.05, max=1.0
    )

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
        
    del bpy.types.Scene.grillz_thickness
    del bpy.types.Scene.grillz_remesh_voxel_size
    del bpy.types.Scene.grillz_decimate_ratio

if __name__ == "__main__":
    register()
