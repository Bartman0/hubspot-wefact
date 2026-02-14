#!/bin/bash

APPNAME=Hubspot-Wefact

mkdir -p "$HOME/Applications/${APPNAME}"

cp "/Volumes/${APPNAME}/hubspot-wefact.db" "$HOME"
cp "/Volumes/${APPNAME}/hubspot-wefact" "$HOME/Applications/${APPNAME}"
cp "/Volumes/${APPNAME}/start.sh" "$HOME/Applications/${APPNAME}"

exit 0
