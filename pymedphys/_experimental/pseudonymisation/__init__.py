from pymedphys._dicom.anonymise import anonymise_cli


def anonymise_with_pseudo_cli(args):
    if args.pseudo:
        print("Was run with pseudo!")

    anonymise_cli(args)
