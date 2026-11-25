"""Install MakeHuman asset packs (zips) into MPFB's user data directory.
Run: Blender -b -P install_packs.py -- <zip> [<zip> ...]"""
import sys, bpy, importlib
mpfb = importlib.import_module("bl_ext.user_default.mpfb")
from bl_ext.user_default.mpfb.services.locationservice import LocationService
from bl_ext.user_default.mpfb.services.assetservice import AssetService
zips = sys.argv[sys.argv.index("--") + 1:]
target = LocationService.get_user_data()
print("USER DATA", target)
for z in zips:
    err = AssetService.check_asset_pack_zip(z)
    if err:
        print("CHECK", z, err)
    res = AssetService.fix_and_extract_asset_pack_zip(z, target)
    print("INSTALLED", z.split("/")[-1], res)
AssetService.update_all_asset_lists()
print("SYSTEM ASSETS", AssetService.system_assets_pack_is_installed())
