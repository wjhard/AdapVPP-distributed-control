import { createApp } from 'vue'
import { use } from 'echarts/core'
import {
  BarChart,
  GaugeChart,
  LineChart,
  LinesChart,
  PictorialBarChart,
} from 'echarts/charts'
import {
  DatasetComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TitleComponent,
  TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import App from './App.vue'
import './style.css'

use([
  BarChart,
  CanvasRenderer,
  DatasetComponent,
  GaugeChart,
  GridComponent,
  LegendComponent,
  LineChart,
  LinesChart,
  MarkAreaComponent,
  MarkLineComponent,
  PictorialBarChart,
  TitleComponent,
  TooltipComponent,
])

createApp(App).mount('#app')
