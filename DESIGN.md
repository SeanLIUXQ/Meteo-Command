# Meteo Command Design System

## Overview

日间环境下，使用者在电脑或手机上快速查询城市天气。浅色界面延续仓库既有蓝灰身份，地图、实时观测和趋势共用稳定的信息层级。

## Colors

Restrained palette: canvas `#f1f4f8`, surface `#ffffff`, sidebar `#f8fafc`, ink `#162b45`, secondary text `#53647a`, border `#dce4ed`, primary action `#2463c5`, selected background `#eaf1fd`。红色 `#a62b35` 表达错误/高风险，褐色 `#83520d` 表达降级/提醒。风险始终同时包含文字。

## Typography

一套系统 sans 字体：Segoe UI、Microsoft YaHei、system-ui。14px 基础字号，24px 主标题，15px 区块标题，61px 当前温度。数字使用 tabular-nums。移动端调整布局和密度，不以超大标题装饰产品。

## Layout

82px 顶栏；桌面 238px 关注侧栏，其余区域为工作区。工作区上方地图与实时天气并列，下方趋势整行展示。980px 以下地图与实时天气叠放；650px 以下关注列表变为横向滚动，内容使用自然页面滚动。

## Components

按钮统一 7px 圆角、明确 hover/focus/disabled 状态；面板 12px 圆角和单线边界。搜索结果菜单跟随搜索框，支持箭头键/回车/Escape。关注城市优先按目录 ID 识别，坐标作为兼容回退；删除操作独立按钮。历史日有浅灰底，今天用浅蓝色；图表和文字预报同源。

## States and Motion

150–180ms 交互状态变化；无装饰动画，图表尊重 prefers-reduced-motion。加载和错误状态使用实际文字；null 显示破折号，不显示零。空气质量失败时保留天气；过期缓存显示数据时间和明确提示。切换城市立即清空旧城市详情并取消过期请求。
