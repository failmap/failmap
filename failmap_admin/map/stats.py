import subprocess


def update_stats():
    return


# --data-binary "naam,organisatie=icf tls_errors=10 $(date +%s -d 2017-11-16T19:00)"
subprocess.call(['curl', '-s', '-XPOST', '"influxdb:8086/write?db=elger_test&precision=s"', '--data-binary'])
