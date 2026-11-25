"""Layout constants shared by every campus module, first ported 1:1 from mano-game/src/level/Campus.js; the south
side of rue Pasteur (Paritalie, 24 rue Pasteur) now uses the real footprints below.
Game space: metres, Y up, X east (along rue Pasteur), Z south. Origin: middle of rue Pasteur."""
import math

FLOOR = 3.6
F1 = FLOOR            # 1st floor of the Batiment Voltaire
UY = -FLOOR           # the Under (BDE basement)
AY = -2.4             # Amphi 4 stage level
X_H = 17.5            # Paritalie (the X) roof level: R+5, IGN 16 m with 19.6 m at the highest point

# X building NE wing courtyard face, from the passage mouth; frame like Builder.frame(NE0, neYaw)
NE0 = (-0.4, 14.0)
NE1 = (-12.3, 24.9)
NE_YAW = math.atan2(-(NE1[1] - NE0[1]), NE1[0] - NE0[0])
NE_LEN = math.hypot(NE1[0] - NE0[0], NE1[1] - NE0[1])
# X building SE wing (cafeteria): courtyard face. The cafeteria frame sits 0.25 m inside it
# because the room's glass front is built at local z = -0.25.
SE_FACE = ((-13.1, 32.3), (-1.8, 44.6))
_se_l = math.hypot(SE_FACE[1][0] - SE_FACE[0][0], SE_FACE[1][1] - SE_FACE[0][1])
_se_in = (-(SE_FACE[1][1] - SE_FACE[0][1]) / _se_l * 0.25, (SE_FACE[1][0] - SE_FACE[0][0]) / _se_l * 0.25)
SE0 = (SE_FACE[0][0] + _se_in[0], SE_FACE[0][1] + _se_in[1])
SE1 = (SE_FACE[1][0] + _se_in[0], SE_FACE[1][1] + _se_in[1])
SE_YAW = math.atan2(-(SE1[1] - SE0[1]), SE1[0] - SE0[0])
SE_LEN = math.hypot(SE1[0] - SE0[0], SE1[1] - SE0[1])
CAFE_D = 9.2          # cafeteria depth (local z)

# Real footprints (docs/CAMPUS_LAYOUT.md §5.1), clockwise in (x, z)
X_PARITALIE = [(-45.2, 4.9), (-47.0, 6.7), (-47.2, 12.7), (-36.0, 24.5), (-37.2, 25.5), (-37.5, 30.7), (-36.3, 32.0),
               (-48.2, 42.9), (-48.4, 48.8), (-46.4, 50.9), (-40.2, 51.1), (-28.3, 39.9), (-27.3, 41.0), (-22.1, 41.2),
               (-20.9, 40.3), (-9.6, 52.1), (-3.8, 52.4), (-1.9, 50.9), (-1.8, 44.6), (-13.1, 32.3), (-11.7, 30.9),
               (-11.6, 25.9), (-12.3, 24.9), (-0.2, 13.9), (0.0, 7.1), (-1.7, 5.0), (-7.5, 5.0), (-20.2, 16.9),
               (-21.2, 15.7), (-26.4, 15.6), (-27.6, 16.7), (-38.7, 4.9)]
EAST_24 = [(9.2, 5.0), (6.7, 7.4), (6.5, 14.3), (10.5, 18.6), (25.8, 18.9), (33.2, 26.6), (33.0, 38.3), (30.6, 38.2),
           (30.6, 39.4), (47.1, 40.0), (45.6, 9.6), (40.8, 5.0)]          # 24 rue Pasteur east building ("Amphi 4")
PASSAGE_N = [(0.0, 7.1), (-0.4, 14.0), (6.5, 14.3), (6.7, 7.4)]           # light roof, gate at (3.0, 7.2)
RECESS_N = [(-1.7, 5.0), (0.0, 7.1), (6.7, 7.4), (9.2, 5.0)]             # open recess between the piers and the roof
PASSAGE_S = [(-1.8, 44.6), (-1.9, 50.4), (5.7, 50.6), (5.9, 44.9)]        # light structure, gate (2.0, 50.5)
SOUTH_W = [(5.9, 44.9), (5.7, 50.6), (7.7, 52.7), (19.8, 53.1), (20.2, 41.4), (10.0, 41.1)]   # 8.4 m
SOUTH_E = [(20.2, 41.4), (19.8, 53.1), (30.0, 53.5), (30.5, 41.7)]                            # 9.3 m
COURT = [(-0.4, 14.0), (-12.3, 24.9), (-11.6, 25.9), (-11.7, 30.9), (-13.1, 32.3), (-8.3, 37.6), (-1.8, 44.6), (5.9, 44.9),
         (10.0, 41.1), (20.2, 41.4), (30.5, 41.7), (30.6, 38.2), (33.0, 38.3), (33.2, 26.6), (29.7, 23.0), (25.8, 18.9),
         (10.5, 18.6), (6.5, 14.3)]                                                            # about 1,030 m2

# Amphi 4
TIERS = 7
TIER_D = 0.95
TIER_H = 0.3
AMPHI_TOP_Z = 16.4    # back edge of tier 1 / front of the entrance landing


def frame_pt(ox, oz, yaw, lx, lz):
    c, s = math.cos(yaw), math.sin(yaw)
    return (ox + lx * c + lz * s, oz - lx * s + lz * c)


def cafe_pt(lx, lz):
    return frame_pt(SE0[0], SE0[1], SE_YAW, lx, lz)


def ne_pt(lx, lz):
    return frame_pt(NE0[0], NE0[1], NE_YAW, lx, lz)


# local -z of the NE wing frame = toward the courtyard
NE_NX = -math.sin(NE_YAW)
NE_NZ = -math.cos(NE_YAW)


def step_seat(t, d=1.5):
    return (NE0[0] + (NE1[0] - NE0[0]) * t + NE_NX * d, NE0[1] + (NE1[1] - NE0[1]) * t + NE_NZ * d, math.atan2(NE_NX, NE_NZ))


def tier(k):
    return {"y": -TIER_H * k, "z": AMPHI_TOP_Z - TIER_D * (k - 0.5)}


def tier_z(k):
    """(z0, z1, top) of amphi tier k (1..7)"""
    z1 = AMPHI_TOP_Z - TIER_D * (k - 1)
    return z1 - TIER_D, z1, -TIER_H * k


def pc_row_xs(x0, x1):
    xs, x = [], x0
    while x <= x1 + 0.01:
        xs.append(round(x, 4))
        x += 1.45
    return xs


PC_ROWS_Z = (-23.6, -20.6, -17.8)
PC_ROW_X = ((-16.6, -6.0), (-2.6, 6.5))
