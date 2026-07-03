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
  MarkLineComponent,
  PictorialBarChart,
  TitleComponent,
  TooltipComponent,
])

createApp(App).mount('#app')
