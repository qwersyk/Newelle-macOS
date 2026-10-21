/* Render through the same GtkIconPaintable path used by GtkImage. */
#include <gtk/gtk.h>

int main(int argc, char **argv) {
    if (argc != 3) return 2;
    gtk_init();
    GFile *file = g_file_new_for_path(argv[1]);
    GdkPaintable *icon = GDK_PAINTABLE(gtk_icon_paintable_new_for_file(file, 220, 1));
    GtkSnapshot *snapshot = gtk_snapshot_new();
    gdk_paintable_snapshot(icon, snapshot, 220, 220);
    GskRenderNode *node = gtk_snapshot_free_to_node(snapshot);
    if (!node) return 3;
    GskRenderer *renderer = gsk_cairo_renderer_new();
    GError *error = NULL;
    if (!gsk_renderer_realize(renderer, NULL, &error)) {
        g_printerr("%s\n", error->message);
        return 4;
    }
    graphene_rect_t viewport = GRAPHENE_RECT_INIT(0, 0, 220, 220);
    GdkTexture *texture = gsk_renderer_render_texture(renderer, node, &viewport);
    gboolean saved = gdk_texture_save_to_png(texture, argv[2]);
    g_object_unref(texture);
    gsk_renderer_unrealize(renderer);
    g_object_unref(renderer);
    gsk_render_node_unref(node);
    g_object_unref(icon);
    g_object_unref(file);
    return saved ? 0 : 5;
}
