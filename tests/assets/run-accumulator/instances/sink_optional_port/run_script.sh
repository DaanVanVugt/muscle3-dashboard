#!/bin/bash

. /home/ITER/sanderm/gitrepos/pds/run/IMAS-MUSCLE3/venv/bin/activate

exec python -u -m imas_muscle3.actors.sink_component
