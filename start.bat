@echo off
title WARDOGS BOTS
if exist requirements_news.txt pip install -r requirements_news.txt
if not exist data mkdir data
python bot.py
pause
