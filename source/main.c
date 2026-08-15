// double_maze -- GBA port of the iOS game.
//
// Two balls share one 15x8 grid, the left playing columns 1-6 and the right
// columns 8-13. Every D-pad press moves BOTH balls in that direction, and each
// is blocked independently by the walls on its own tile edges. Land on a hole
// and you restart; get both balls onto goal tiles at once and you advance.
//
// See EXTRACTION.md for where each rule came from in the original.

#include <tonc.h>

#include "audio.h"
#include "ball.h"
#include "levels.h"
#include "render.h"
#include "save.h"
#include "skins.h"

// The original slides the ball over 0.4s. That's sluggish with a D-pad, where
// there's no swipe gesture to perform first, so this is a little quicker.
#define MOVE_FRAMES  12
#define DEATH_FRAMES 90   // the iOS build waits 1.5s before restarting
#define WIN_FRAMES   60   // ...and 1.0s before advancing

#define DEATH_ANIM_HOLD 4 // frames per death-animation frame

#define SELECT_COLS 7   // 7 cells of 4 columns, plus room for the cursor
#define SELECT_ROWS ((LEVEL_COUNT + SELECT_COLS - 1) / SELECT_COLS)

typedef enum AppState
{
    APP_TITLE,
    APP_HELP,
    APP_SELECT,
    APP_PLAY,
    APP_DEATH,
    APP_WIN,
} AppState;

typedef struct Ball
{
    int  cx, cy;            // grid cell; may sit off-grid after a fatal step
    int  px, py;            // current pixel position
    int  from_x, from_y;    // where the current slide started
    int  slide;             // frames left in the slide, 0 when settled
    bool alive;
} Ball;

static const LevelData *g_level;
static int       g_level_index;
static int       g_skin;
static Ball      g_ball[2];
static AppState  g_state;
static int       g_timer;
static int       g_menu_cursor;
static bool      g_was_on_goal[2];   // goal state before the current step
static OBJ_ATTR  g_obj_buffer[128];

//---------------------------------------------------------------------------
// grid helpers

static inline u8 flags_at(int x, int y)
{
    return g_level->flags[y * GRID_W + x];
}

static inline bool on_grid(int x, int y)
{
    return x >= 0 && y >= 0 && x < GRID_W && y < GRID_H;
}

static inline int cell_to_px(int cx) { return cx * CELL_PX; }
static inline int cell_to_py(int cy) { return GRID_TOP_PX + cy * CELL_PX; }

//---------------------------------------------------------------------------
// movement

// A step is legal when the current tile's edge is open AND the target tile's
// opposite edge is open. Stepping off the grid is deliberately allowed --
// that's one of the ways the original kills you.
static bool step_ball(Ball *b, int dx, int dy)
{
    if (!b->alive)
        return false;

    u8 leaving, entering;
    if      (dy < 0) { leaving = WALL_UP;    entering = WALL_DOWN;  }
    else if (dy > 0) { leaving = WALL_DOWN;  entering = WALL_UP;    }
    else if (dx < 0) { leaving = WALL_LEFT;  entering = WALL_RIGHT; }
    else             { leaving = WALL_RIGHT; entering = WALL_LEFT;  }

    if (flags_at(b->cx, b->cy) & leaving)
        return false;

    int nx = b->cx + dx;
    int ny = b->cy + dy;

    bool off = !on_grid(nx, ny);
    if (!off && (flags_at(nx, ny) & entering))
        return false;

    b->from_x = b->px;
    b->from_y = b->py;
    b->cx = nx;
    b->cy = ny;
    b->slide = MOVE_FRAMES;

    if (off || (flags_at(nx, ny) & FLAG_DEATH))
        b->alive = false;

    return true;
}

static void advance_slide(Ball *b)
{
    if (b->slide <= 0)
        return;

    b->slide--;

    int to_x = cell_to_px(b->cx);
    int to_y = cell_to_py(b->cy);
    int done = MOVE_FRAMES - b->slide;

    b->px = b->from_x + (to_x - b->from_x) * done / MOVE_FRAMES;
    b->py = b->from_y + (to_y - b->from_y) * done / MOVE_FRAMES;
}

static bool any_sliding(void)
{
    return g_ball[0].slide > 0 || g_ball[1].slide > 0;
}

static bool ball_on_goal(const Ball *b)
{
    return b->alive && on_grid(b->cx, b->cy) &&
           (flags_at(b->cx, b->cy) & FLAG_FINISH);
}

//---------------------------------------------------------------------------
// drawing

static void hide_all_sprites(void)
{
    for (int i = 0; i < 2; i++)
        obj_hide(&g_obj_buffer[i]);
}

static void update_sprites(void)
{
    // During the death sequence both balls freeze and the dead one plays the
    // shrink-and-fade frames from the original's balldeath set.
    int death_frame = -1;
    if (g_state == APP_DEATH)
    {
        int elapsed = DEATH_FRAMES - g_timer;
        death_frame = elapsed / DEATH_ANIM_HOLD;
        if (death_frame >= SPR_DEATH_COUNT)
            death_frame = SPR_DEATH_COUNT;   // one past the end: hide it
    }

    for (int i = 0; i < 2; i++)
    {
        OBJ_ATTR *obj = &g_obj_buffer[i];
        Ball *b = &g_ball[i];

        // A ball that stepped onto a hole is already flagged dead, but it
        // still has to finish sliding into that tile -- hiding it or starting
        // the death frames now would make it vanish mid-move and pop back at
        // the destination. Keep drawing the plain ball until it lands.
        int metatile = SPR_BALL;
        if (!b->alive && b->slide == 0)
        {
            if (death_frame < 0 || death_frame >= SPR_DEATH_COUNT)
            {
                obj_hide(obj);
                continue;
            }
            metatile = SPR_DEATH_FIRST + death_frame;
        }

        obj_unhide(obj, 0);
        obj_set_attr(obj,
                     ATTR0_SQUARE | ATTR0_4BPP,
                     ATTR1_SIZE_16,
                     ATTR2_PALBANK(0) | (metatile * MT_TILES));
        obj_set_pos(obj, b->px, b->py);
    }
}

// Goal tiles light up while a ball is standing on them, which is the game's
// only feedback that half the puzzle is solved.
static void refresh_goal_lights(void)
{
    for (int cy = 0; cy < GRID_H; cy++)
    {
        for (int cx = 0; cx < GRID_W; cx++)
        {
            if (!(g_level->flags[cy * GRID_W + cx] & FLAG_FINISH))
                continue;

            bool lit = false;
            for (int i = 0; i < 2; i++)
                if (g_ball[i].alive && g_ball[i].cx == cx && g_ball[i].cy == cy)
                    lit = true;

            render_cell(g_level, g_skin, cx, cy, lit);
        }
    }
}

//---------------------------------------------------------------------------
// level lifecycle

static void load_level(int index)
{
    g_level_index = index;
    g_level = &g_levels[index];

    // The original cycles skin and background every two levels rather than
    // picking at random: floor(level / 2) % 3.
    g_skin = (index / 2) % SKIN_COUNT;

    g_ball[0].cx = g_level->left_x;
    g_ball[0].cy = g_level->left_y;
    g_ball[1].cx = g_level->right_x;
    g_ball[1].cy = g_level->right_y;

    for (int i = 0; i < 2; i++)
    {
        g_ball[i].px = g_ball[i].from_x = cell_to_px(g_ball[i].cx);
        g_ball[i].py = g_ball[i].from_y = cell_to_py(g_ball[i].cy);
        g_ball[i].slide = 0;
        g_ball[i].alive = true;
    }

    for (int i = 0; i < 2; i++)
        g_was_on_goal[i] = ball_on_goal(&g_ball[i]);

    g_state = APP_PLAY;
    g_timer = 0;

    render_level(g_level, g_skin);
    render_hud(g_level->number);
    refresh_goal_lights();
}

static void complete_level(void)
{
    g_save.completed[g_level_index] = 1;
    g_save.last_level = (u8)g_level_index;
    save_store();
}

static void advance_level(void)
{
    load_level((g_level_index + 1) % LEVEL_COUNT);
}

//---------------------------------------------------------------------------
// menus

static void draw_title(void)
{
    render_title_art();
    render_text_centred(13, "PRESS START");
    render_text_centred(15, "A - PLAY   B - HOW TO");
    render_text_centred(17, g_save.music_on ? "SELECT - MUSIC ON"
                                            : "SELECT - MUSIC OFF");
#ifdef AUDIO_DEBUG
    // Reports whether the music effect actually took a mixer channel, since
    // the capture pipeline can't hear anything. Build with
    //   make DEFINES=-DAUDIO_DEBUG
    {
        char line[] = "SFX H:__ ACT:_";
        int h = audio_music_handle();
        line[7]  = '0' + (h / 10) % 10;
        line[8]  = '0' + h % 10;
        line[13] = audio_music_playing() ? 'Y' : 'N';
        render_text_centred(19, line);
    }
#endif
}

static void draw_help(void)
{
    render_plain(0);
    render_text_centred(1, "HOW TO PLAY");

    // Every other row: the glyphs' drop shadow sits on the bottom pixel line
    // of the cell, so consecutive rows would butt right up against each other.
    render_text(3,  4, "THE D-PAD MOVES");
    render_text(3,  6, "BOTH BALLS AT ONCE.");
    render_text(3,  9, "EACH IS BLOCKED BY");
    render_text(3, 11, "ITS OWN WALLS.");
    render_text(3, 14, "LAND BOTH ON GOALS.");

    render_text_centred(17, "B - BACK");
}

static void draw_select(void)
{
    render_plain(2);
    render_text_centred(1, "SELECT LEVEL");

    for (int i = 0; i < LEVEL_COUNT; i++)
    {
        // 4-column stride leaves a gap after the completion tick, so the
        // numbers don't run into each other.
        int row = 4 + (i / SELECT_COLS) * 2;
        int col = 2 + (i % SELECT_COLS) * 4;

        char cell[4];
        cell[0] = '0' + (g_levels[i].number / 10) % 10;
        cell[1] = '0' + g_levels[i].number % 10;
        cell[2] = g_save.completed[i] ? '*' : ' ';
        cell[3] = '\0';
        render_text(col, row, cell);

        if (i == g_menu_cursor)
            render_text(col - 1, row, ">");
    }

    render_text_centred(17, "A - PLAY   B - BACK");
}

static void goto_state(AppState s)
{
    g_state = s;
    hide_all_sprites();

    switch (s)
    {
    case APP_TITLE:  draw_title();  break;
    case APP_HELP:   draw_help();   break;
    case APP_SELECT: draw_select(); break;
    default: break;
    }
}

//---------------------------------------------------------------------------
// per-state input

static void input_title(void)
{
    if (key_hit(KEY_START) || key_hit(KEY_A))
    {
        audio_play(SND_PAGE);
        g_menu_cursor = g_save.last_level;
        goto_state(APP_SELECT);
    }
    else if (key_hit(KEY_B))
    {
        audio_play(SND_PAGE);
        goto_state(APP_HELP);
    }
    else if (key_hit(KEY_SELECT))
    {
        audio_play(SND_UI);
        g_save.music_on = !g_save.music_on;
        audio_music_set(g_save.music_on);
        save_store();
        draw_title();
    }
}

static void input_help(void)
{
    if (key_hit(KEY_B) || key_hit(KEY_START) || key_hit(KEY_A))
    {
        audio_play(SND_PAGE);
        goto_state(APP_TITLE);
    }
}

static void input_select(void)
{
    int move = 0;
    if      (key_hit(KEY_LEFT))  move = -1;
    else if (key_hit(KEY_RIGHT)) move =  1;
    else if (key_hit(KEY_UP))    move = -SELECT_COLS;
    else if (key_hit(KEY_DOWN))  move =  SELECT_COLS;

    if (move)
    {
        int next = g_menu_cursor + move;
        if (next >= 0 && next < LEVEL_COUNT)
        {
            g_menu_cursor = next;
            audio_play(SND_UI);
            draw_select();
        }
    }

    if (key_hit(KEY_A) || key_hit(KEY_START))
    {
        audio_play(SND_PAGE);
        load_level(g_menu_cursor);
    }
    else if (key_hit(KEY_B))
    {
        audio_play(SND_PAGE);
        goto_state(APP_TITLE);
    }
}

static void input_play(void)
{
    if (key_hit(KEY_B))
    {
        audio_play(SND_PAGE);
        g_menu_cursor = g_level_index;
        goto_state(APP_SELECT);
        return;
    }
    if (key_hit(KEY_START))
    {
        advance_level();            // the iOS "skip" button
        return;
    }
    if (key_hit(KEY_SELECT))
    {
        load_level(g_level_index);  // restart
        return;
    }

    // Input is locked while the balls are in motion, mirroring the original's
    // isAnimating flag.
    if (any_sliding())
        return;

    int dx = 0, dy = 0;
    if      (key_hit(KEY_UP))    dy = -1;
    else if (key_hit(KEY_DOWN))  dy =  1;
    else if (key_hit(KEY_LEFT))  dx = -1;
    else if (key_hit(KEY_RIGHT)) dx =  1;

    if (dx == 0 && dy == 0)
        return;

    // The goal chime marks arriving on a goal, so remember where each ball
    // stood before the step -- otherwise a ball already sitting on one
    // re-triggers it every time the other ball moves.
    for (int i = 0; i < 2; i++)
        g_was_on_goal[i] = ball_on_goal(&g_ball[i]);

    // One press, both balls, same direction. Each is blocked on its own.
    bool moved = step_ball(&g_ball[0], dx, dy);
    moved |= step_ball(&g_ball[1], dx, dy);

    if (moved)
        audio_play(SND_MOVE);
}

// Runs once the balls have finished sliding, so the outcome lands on the beat
// of the animation rather than the button press.
static void settle_step(void)
{
    refresh_goal_lights();

    if (!g_ball[0].alive || !g_ball[1].alive)
    {
        g_state = APP_DEATH;
        g_timer = DEATH_FRAMES;
        audio_play(SND_FALL);
        return;
    }

    bool left_home = ball_on_goal(&g_ball[0]);
    bool right_home = ball_on_goal(&g_ball[1]);

    if (left_home && right_home)
    {
        g_state = APP_WIN;
        g_timer = WIN_FRAMES;
        complete_level();
        audio_play(SND_COMPLETE);
    }
    else if ((left_home && !g_was_on_goal[0]) ||
             (right_home && !g_was_on_goal[1]))
    {
        // Chime only on arrival. A ball that was already home and stayed put
        // isn't news, and re-announcing it every move gets grating.
        audio_play(SND_GOAL);
    }
}

//---------------------------------------------------------------------------

int main(void)
{
    irq_init(NULL);

    save_load();

    render_init();
    audio_init();
    audio_music_set(g_save.music_on);

    memcpy32(tile_mem_obj[0], ballTiles, ballTilesLen / 4);
    memcpy16(pal_obj_mem, ballPal, 16);
    oam_init(g_obj_buffer, 128);

#ifdef BOOT_LEVEL
    // Debug shortcut for tools/grab_screen.py: build with
    //   make DEFINES=-DBOOT_LEVEL=0
    // to skip the menus and drop straight into a level. Adding -DBOOT_DEATH
    // also starts, and endlessly repeats, the death sequence.
    load_level(BOOT_LEVEL);
#ifdef BOOT_DEATH
    g_ball[0].alive = false;
    g_state = APP_DEATH;
    g_timer = DEATH_FRAMES;
#endif
#else
    goto_state(APP_TITLE);
#endif

    while (1)
    {
        VBlankIntrWait();
        key_poll();

        bool was_sliding = any_sliding();
        advance_slide(&g_ball[0]);
        advance_slide(&g_ball[1]);

        switch (g_state)
        {
        case APP_TITLE:  input_title();  break;
        case APP_HELP:   input_help();   break;
        case APP_SELECT: input_select(); break;

        case APP_PLAY:
            if (was_sliding && !any_sliding())
                settle_step();
            else
                input_play();
            break;

        case APP_DEATH:
            if (--g_timer <= 0)
            {
#ifdef BOOT_DEATH
                // Debug: loop the death sequence so tools/grab_screen.py can
                // capture it without a way to inject button presses.
                g_ball[0].alive = false;
                g_timer = DEATH_FRAMES;
#else
                load_level(g_level_index);
#endif
            }
            break;

        case APP_WIN:
            if (--g_timer <= 0)
                advance_level();
            break;
        }

        if (g_state == APP_PLAY || g_state == APP_DEATH || g_state == APP_WIN)
            update_sprites();

        oam_copy(oam_mem, g_obj_buffer, 2);
        audio_frame();
    }
}
