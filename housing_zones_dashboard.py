import dash
from dash import dcc, html, Input, Output, State
import plotly.express as px
import pandas as pd
import numpy as np
import geopandas as gpd
from shapely.geometry import Point

# Initialise Dash app
app = dash.Dash(__name__)

# Load data once at startup
print("Loading data...")
migrations_flows = pd.read_csv('flow_data/migration_flow_la_2023.csv')
commuting_flows = pd.read_csv('flow_data/commuting_flow_la_2023.csv')
la_2023_shape_file = '/Users/user1/Documents/housing_zones/Local_Authority_Districts_May_2023_UK_BFE_V2_5074811840009224353'
gdf_la_2023 = gpd.read_file(la_2023_shape_file)
gdf_la_2023 = gdf_la_2023[gdf_la_2023['LAD23CD'].str.startswith(('E', 'W'))]

# Standardise column names
migrations_flows_clean = migrations_flows.rename(columns={
    'outla': 'origin',
    'inla': 'destination',
    'moves': 'flow'
})

commuting_flows_clean = commuting_flows.rename(columns={
    'RES_LAD23CD': 'origin',
    'WORK_LAD23CD': 'destination'
})

print("Data loaded")

# Define helper functions
def create_flow_dict(flow_df):
    """Convert flow DataFrame to nested dict: {origin: {destination: flow}}"""
    flow_dict = {}
    for _, row in flow_df.iterrows():
        origin = row['origin']
        dest = row['destination']
        flow = row['flow']
        
        if origin not in flow_dict:
            flow_dict[origin] = {}
        flow_dict[origin][dest] = flow
    
    return flow_dict

def build_neighbors_dict(gdf):
    """Find neighboring LAs based on shared boundaries"""
    neighbors = {}
    
    for idx1, row1 in gdf.iterrows():
        la1 = row1['LAD23CD']
        neighbors[la1] = set()
        
        for idx2, row2 in gdf.iterrows():
            if idx1 != idx2:
                la2 = row2['LAD23CD']
                if row1.geometry.touches(row2.geometry) or row1.geometry.intersects(row2.geometry):
                    neighbors[la1].add(la2)
    
    return neighbors

def self_containment(region_las, flows_dict):
    """Calculate self-containment for a set of LAs"""
    internal_flow = 0
    total_flow = 0
    
    for origin in region_las:
        if origin not in flows_dict:
            continue
        for dest, flow in flows_dict[origin].items():
            total_flow += flow
            if dest in region_las:
                internal_flow += flow
    
    if total_flow == 0:
        return 0
    return internal_flow / total_flow

def bidirectional_flows(region_a, region_b, flows_dict):
    """Calculate sum of flows in both directions between two regions"""
    flow = 0
    
    for origin in region_a:
        if origin not in flows_dict:
            continue
        for dest in region_b:
            if dest in flows_dict[origin]:
                flow += flows_dict[origin][dest]
    
    for origin in region_b:
        if origin not in flows_dict:
            continue
        for dest in region_a:
            if dest in flows_dict[origin]:
                flow += flows_dict[origin][dest]
    
    return flow

# Pre-compute expensive operations
print("Building flow dictionaries...")
commuting_flows_la = create_flow_dict(commuting_flows_clean)
migration_flows_la = create_flow_dict(migrations_flows_clean)

print("Building neighbourhood graph...")
neighbors = build_neighbors_dict(gdf_la_2023)

print("✓ Pre-processing complete")

# Global variable to store latest results for download
current_results = None

# Major cities for map overlay
major_cities_wgs84 = {
    'London': (-0.1276, 51.5074),
    'Birmingham': (-1.8904, 52.4862),
    'Manchester': (-2.2426, 53.4808),
    'Leeds': (-1.5491, 53.8008),
    'Liverpool': (-2.9916, 53.4084),
    'Sheffield': (-1.4701, 53.3811),
    'Bristol': (-2.5879, 51.4545),
    'Newcastle': (-1.6178, 54.9783),
    'Cardiff': (-3.1791, 51.4816),
    'Leicester': (-1.1332, 52.6369),
}

city_data = []
for city, (lon, lat) in major_cities_wgs84.items():
    city_data.append({'city': city, 'geometry': Point(lon, lat)})

cities_gdf = gpd.GeoDataFrame(city_data, crs='EPSG:4326')

# App layout 
app.layout = html.Div([
    # Header Section
    html.Div([
        html.Div([
            html.H1("Housing Market Areas Creator", 
                    style={
                        'textAlign': 'center', 
                        'color': 'white', 
                        'marginBottom': 10,
                        'fontWeight': '600',
                        'fontSize': 42,
                        'letterSpacing': '-0.5px'
                    }),
            html.P("",
                   style={
                       'textAlign': 'center',
                       'color': 'rgba(255,255,255,0.9)',
                       'fontSize': 16,
                       'marginBottom': 0
                   })
        ], style={
            'background': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            'padding': '40px 20px',
            'borderRadius': '0 0 20px 20px',
            'boxShadow': '0 4px 6px rgba(0,0,0,0.1)'
        })
    ]),
    
    # Main Content
    html.Div([
        # Controls Card
        html.Div([
            html.H3("Algorithm Parameters", 
                    style={'color': '#2c3e50', 'marginBottom': 25, 'fontSize': 22, 'fontWeight': '600'}),
            
            # Sliders Container
            html.Div([
                html.Div([
                    html.Label("Commuting Self-Containment Threshold:", 
                              style={'fontWeight': '600', 'fontSize': 15, 'color': '#34495e', 'marginBottom': 10}),
                    dcc.Slider(
                        id='commuting-slider',
                        min=0.5,
                        max=0.9,
                        step=0.025,
                        value=0.725,
                        marks={i/100: {'label': f'{i}%', 'style': {'fontSize': 12}} for i in range(50, 91, 10)},
                        tooltip={"placement": "bottom", "always_visible": True}
                    ),
                ], style={'marginBottom': 30}),
                
                html.Div([
                    html.Label("Migration Self-Containment Threshold:", 
                              style={'fontWeight': '600', 'fontSize': 15, 'color': '#34495e', 'marginBottom': 10}),
                    dcc.Slider(
                        id='migration-slider',
                        min=0.3,
                        max=0.7,
                        step=0.025,
                        value=0.55,
                        marks={i/100: {'label': f'{i}%', 'style': {'fontSize': 12}} for i in range(30, 71, 10)},
                        tooltip={"placement": "bottom", "always_visible": True}
                    ),
                ], style={'marginBottom': 30}),
            ]),
            
            # Buttons
            html.Div([
                html.Button('Run Algorithm', id='run-button', n_clicks=0,
                           className='primary-button',
                           style={
                               'fontSize': 16, 
                               'padding': '14px 35px',
                               'backgroundColor': '#667eea',
                               'color': 'white',
                               'border': 'none',
                               'borderRadius': 8,
                               'cursor': 'pointer',
                               'fontWeight': '600',
                               'marginRight': 15,
                               'boxShadow': '0 2px 4px rgba(102,126,234,0.3)',
                               'transition': 'all 0.3s ease'
                           }),
                html.Button('Download Results CSV', id='download-button',
                           className='secondary-button',
                           style={
                               'fontSize': 16, 
                               'padding': '14px 35px',
                               'backgroundColor': '#27ae60',
                               'color': 'white',
                               'border': 'none',
                               'borderRadius': 8,
                               'cursor': 'pointer',
                               'fontWeight': '600',
                               'boxShadow': '0 2px 4px rgba(39,174,96,0.3)',
                               'transition': 'all 0.3s ease'
                           }),
                dcc.Download(id='download-dataframe-csv')
            ], style={'textAlign': 'center', 'marginTop': 10}),
            
        ], style={
            'backgroundColor': 'white',
            'padding': 30,
            'borderRadius': 12,
            'boxShadow': '0 2px 8px rgba(0,0,0,0.08)',
            'marginBottom': 25
        }),
        
        # Status Message
        html.Div(id='status-message', style={
            'textAlign': 'center', 
            'fontSize': 15,
            'marginBottom': 20,
            'color': '#7f8c8d',
            'fontWeight': '500',
            'padding': '10px',
            'borderRadius': 8
        }),
        
        # Map Card
        html.Div([
            dcc.Loading(
                id="loading",
                type="circle",
                color="#667eea",
                children=[
                    dcc.Graph(id='hma-map', 
                             style={'height': '75vh', 'borderRadius': 8},
                             config={'displayModeBar': True, 'displaylogo': False}),
                ]
            ),
        ], style={
            'backgroundColor': 'white',
            'padding': 15,
            'borderRadius': 12,
            'boxShadow': '0 2px 8px rgba(0,0,0,0.08)',
            'marginBottom': 25
        }),
        
        # Stats Card
        html.Div(id='stats-output', style={
            'backgroundColor': 'white',
            'padding': 30,
            'borderRadius': 12,
            'boxShadow': '0 2px 8px rgba(0,0,0,0.08)'
        })
        
    ], style={
        'maxWidth': 1400,
        'margin': '0 auto',
        'padding': '30px 20px'
    })
], style={
    'backgroundColor': '#f5f7fa',
    'minHeight': '100vh',
    'fontFamily': '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
})

@app.callback(
    [Output('hma-map', 'figure'),
     Output('stats-output', 'children'),
     Output('status-message', 'children')],
    [Input('run-button', 'n_clicks')],
    [State('commuting-slider', 'value'),
     State('migration-slider', 'value')],
    prevent_initial_call=False
)
def run_algorithm(n_clicks, commuting_threshold, migration_threshold):
    print(f"\n{'='*80}")
    print(f"=== CALLBACK TRIGGERED ===")
    print(f"n_clicks={n_clicks}, commuting={commuting_threshold}, migration={migration_threshold}")
    print(f"{'='*80}")
    
    try:
        if n_clicks == 0:
            print("Initial load, returning empty figure")
            # Return empty figure on initial load
            empty_fig = px.choropleth_mapbox(
                mapbox_style='carto-positron',
                center={"lat": 52.5, "lon": -2},
                zoom=5.5
            )
            empty_fig.update_layout(
                margin={"r":0,"t":60,"l":0,"b":0},
                title="Click 'Run Algorithm' to generate Housing Market Areas"
            )
            print("✓ Empty figure created successfully")
            return empty_fig, "", "Adjust thresholds and click 'Run Algorithm' to begin"
        
        print(f"\n{'='*80}")
        print(f"STARTING ALGORITHM")
        print(f"Commuting threshold: {commuting_threshold:.1%}")
        print(f"Migration threshold: {migration_threshold:.1%}")
        print(f"{'='*80}")
        
        # STEP 1: Building commuting-based areas
        print("\n--- STEP 1: Building commuting-based areas ---")
        print(f"Initialising {len(gdf_la_2023)} LAs as individual regions...")
        commuting_regions = {la: {la} for la in gdf_la_2023['LAD23CD']}
        print(f"✓ Created {len(commuting_regions)} initial regions")
        
        print("Calculating initial self-containment scores...")
        sc_cache_commuting = {la: self_containment({la}, commuting_flows_la)
                              for la in commuting_regions.keys()}
        print(f"✓ Calculated self-containment for {len(sc_cache_commuting)} regions")
        
        iteration = 0
        max_iterations = 2000
        
        print(f"Starting greedy agglomeration (max {max_iterations} iterations)...")
        while iteration < max_iterations:
            iteration += 1
            
            failing_regions = [region_id for region_id, sc in sc_cache_commuting.items() 
                              if sc < commuting_threshold]
            
            if not failing_regions:
                print(f"✓ All regions meet {commuting_threshold:.1%} threshold after {iteration-1} iterations")
                break
            
            if iteration % 50 == 0:
                print(f"  Iteration {iteration}: {len(commuting_regions)} regions, {len(failing_regions)} below threshold")
            
            best_pair_id = None
            best_flow = 0
            
            try:
                for region_id in failing_regions:
                    r = commuting_regions[region_id]
                    
                    r_neighbors = set()
                    for la in r:
                        if la in neighbors:
                            r_neighbors.update(neighbors[la])
                    r_neighbors = r_neighbors - r
                    
                    for other_id, s in commuting_regions.items():
                        if other_id == region_id:
                            continue
                        if not r_neighbors.intersection(s):
                            continue
                        
                        flow = bidirectional_flows(r, s, commuting_flows_la)
                        if flow > best_flow:
                            best_flow = flow
                            best_pair_id = (region_id, other_id)
            except Exception as e:
                print(f"ERROR in iteration {iteration}: {str(e)}")
                import traceback
                traceback.print_exc()
                break
            
            if best_pair_id is None:
                print(f"  No valid merges found at iteration {iteration}. Stopping.")
                break
            
            i, j = best_pair_id
            merged = commuting_regions[i] | commuting_regions[j]
            
            del commuting_regions[i]
            del commuting_regions[j]
            del sc_cache_commuting[i]
            del sc_cache_commuting[j]
            
            new_id = f"R_{iteration}"
            commuting_regions[new_id] = merged
            sc_cache_commuting[new_id] = self_containment(merged, commuting_flows_la)
        
        print(f"✓ Step 1 complete: Created {len(commuting_regions)} commuting-based regions")
        
        # STEP 2: Testing migration closure
        print("\n--- STEP 2: Testing migration closure ---")
        passed_regions = {}
        failed_las = set()
        
        print("Testing each region against migration threshold...")
        for idx, (region_id, region_las) in enumerate(commuting_regions.items()):
            try:
                migration_sc = self_containment(region_las, migration_flows_la)
                
                if migration_sc >= migration_threshold:
                    passed_regions[region_id] = region_las
                else:
                    failed_las.update(region_las)
                
                if (idx + 1) % 20 == 0:
                    print(f"  Tested {idx + 1}/{len(commuting_regions)} regions...")
            except Exception as e:
                print(f"ERROR testing region {region_id}: {str(e)}")
                import traceback
                traceback.print_exc()
        
        print(f"✓ Passed: {len(passed_regions)} regions ({sum(len(r) for r in passed_regions.values())} LAs)")
        print(f"✗ Failed: {len(failed_las)} LAs need re-grouping")
        
        # STEP 3: Re-grouping failed LAs using migration flows
        print("\n--- STEP 3: Re-grouping failed LAs ---")
        migration_regions = {la: {la} for la in failed_las}
        print(f"Initialising {len(migration_regions)} failed LAs for re-grouping...")
        
        sc_cache_migration = {la: self_containment({la}, migration_flows_la)
                              for la in migration_regions.keys()}
        print(f"✓ Calculated migration self-containment for {len(sc_cache_migration)} LAs")
        
        iteration = 0
        
        print("Starting migration-based agglomeration...")
        while iteration < max_iterations:
            iteration += 1
            
            failing_regions = [region_id for region_id, sc in sc_cache_migration.items()
                              if sc < migration_threshold]
            
            if not failing_regions:
                print(f"✓ All regions meet {migration_threshold:.1%} threshold after {iteration-1} iterations")
                break
            
            if iteration % 50 == 0:
                print(f"  Iteration {iteration}: {len(migration_regions)} regions, {len(failing_regions)} below threshold")
            
            best_pair_id = None
            best_flow = 0
            
            try:
                for region_id in failing_regions:
                    r = migration_regions[region_id]
                    
                    r_neighbors = set()
                    for la in r:
                        if la in neighbors:
                            r_neighbors.update(neighbors[la])
                    r_neighbors = r_neighbors - r
                    
                    for other_id, s in migration_regions.items():
                        if other_id == region_id:
                            continue
                        if not r_neighbors.intersection(s):
                            continue
                        
                        flow = bidirectional_flows(r, s, migration_flows_la)
                        if flow > best_flow:
                            best_flow = flow
                            best_pair_id = (region_id, other_id)
            except Exception as e:
                print(f"ERROR in migration iteration {iteration}: {str(e)}")
                import traceback
                traceback.print_exc()
                break
            
            if best_pair_id is None:
                print(f"  No valid merges found at iteration {iteration}. Stopping.")
                break
            
            i, j = best_pair_id
            merged = migration_regions[i] | migration_regions[j]
            
            del migration_regions[i]
            del migration_regions[j]
            del sc_cache_migration[i]
            del sc_cache_migration[j]
            
            new_id = f"M_{iteration}"
            migration_regions[new_id] = merged
            sc_cache_migration[new_id] = self_containment(merged, migration_flows_la)
        
        print(f"✓ Step 3 complete: Created {len(migration_regions)} migration-based regions")
        
        # Combine results
        print("\n--- FINAL: Combining results ---")
        final_hmas = {}
        final_hmas.update(passed_regions)
        final_hmas.update(migration_regions)
        print(f"✓ Combined {len(passed_regions)} passed + {len(migration_regions)} re-grouped = {len(final_hmas)} total HMAs")
        
        # Create DataFrame
        print("Creating DataFrame...")
        hma_list = []
        
        for hma_id, (region_id, region_las) in enumerate(final_hmas.items()):
            try:
                commuting_sc = self_containment(region_las, commuting_flows_la)
                migration_sc = self_containment(region_las, migration_flows_la)
                
                for la in region_las:
                    hma_list.append({
                        "LAD23CD": la,
                        "HMA_ID": hma_id,
                        "HMA_Name": region_id,
                        "HMA_Size": len(region_las),
                        "Commuting_SC": commuting_sc,
                        "Migration_SC": migration_sc
                    })
            except Exception as e:
                print(f"ERROR creating DataFrame entry for HMA {hma_id}: {str(e)}")
                import traceback
                traceback.print_exc()
        
        combined_hma_df = pd.DataFrame(hma_list)
        print(f"✓ Created DataFrame with {len(combined_hma_df)} rows")
        
        # Store results globally for download
        global current_results
        current_results = combined_hma_df.copy()
        
        # Prepare map data
        print("Preparing map data...")
        try:
            gdf_hma_dissolved = gdf_la_2023.merge(combined_hma_df, on='LAD23CD', how='left').dissolve(
                by='HMA_ID', aggfunc='first').reset_index()
            print(f"✓ Dissolved geometries into {len(gdf_hma_dissolved)} HMA polygons")
            
            gdf_hma_dissolved = gdf_hma_dissolved.to_crs(epsg=4326)
            print("✓ Converted to WGS84 coordinate system")
            
            geojson_hma = gdf_hma_dissolved.__geo_interface__
            print("✓ Created GeoJSON")
        except Exception as e:
            print(f"ERROR preparing map data: {str(e)}")
            import traceback
            traceback.print_exc()
            raise
        
        # Create Plotly map
        print("Creating Plotly map...")
        try:
            title = f'Housing Market Areas: {commuting_threshold:.1%} Commuting + {migration_threshold:.1%} Migration Closure'
            
            # Convert HMA_ID to string for categorical coloring
            gdf_hma_dissolved['HMA_ID_str'] = gdf_hma_dissolved['HMA_ID'].astype(str)
            print(f"✓ Converted HMA_ID to categorical")
            
            # Clean data for JSON serialisation - keep only needed columns
            print("Cleaning data for serialisation...")
            plot_df = gdf_hma_dissolved[['HMA_ID', 'HMA_Name', 'HMA_Size', 'Commuting_SC', 'Migration_SC', 'geometry']].copy()
            plot_df = plot_df.fillna({'HMA_Name': 'Unnamed', 'HMA_Size': 0})
            # Round numeric columns to reduce JSON size
            plot_df['Commuting_SC'] = plot_df['Commuting_SC'].round(4)
            plot_df['Migration_SC'] = plot_df['Migration_SC'].round(4)
            plot_df['HMA_ID_str'] = plot_df['HMA_ID'].astype(str)
            print(f"✓ Cleaned data - using {len(plot_df.columns)} columns")
            
            # Simplify GeoJSON - use lower precision and coordinate rounding
            print("Simplifying geometries...")
            plot_df_simplified = plot_df.copy()
            plot_df_simplified['geometry'] = plot_df_simplified.geometry.simplify(tolerance=0.005, preserve_topology=True)
            # Convert to GeoJSON with reduced precision
            import json
            geojson_simplified = json.loads(plot_df_simplified.to_json(drop_id=True, to_wgs84=False))
            # Verify feature count matches
            print(f"✓ Simplified GeoJSON: {len(geojson_simplified['features'])} features")
            
            # Create figure with explicit color mapping to ensure unique colors
            fig = px.choropleth_mapbox(
                plot_df,
                geojson=geojson_simplified,
                locations='HMA_ID',
                featureidkey='properties.HMA_ID',
                color='HMA_ID_str',
                hover_name='HMA_Name',
                hover_data={
                    'HMA_ID': True,
                    'HMA_ID_str': False,
                    'HMA_Size': True,
                    'Commuting_SC': ':.1%',
                    'Migration_SC': ':.1%'
                },
                mapbox_style='carto-positron',
                center={"lat": 52.5, "lon": -2},
                zoom=5.5,
                opacity=0.7,
                title=title,
                color_discrete_sequence=px.colors.qualitative.Light24 + px.colors.qualitative.Dark24
            )
            print(f"✓ Created choropleth with {len(plot_df)} HMA polygons")
            print("✓ Created choropleth map")
            
            # Add major cities
            fig.add_scattermapbox(
                lat=cities_gdf.geometry.y,
                lon=cities_gdf.geometry.x,
                mode='markers+text',
                marker=dict(size=8, color='red'),
                text=cities_gdf['city'],
                textposition='top right',
                textfont=dict(size=10, color='darkred'),
                name='Major Cities'
            )
            print("✓ Added major cities overlay")
            
            fig.update_layout(
                margin={"r":0,"t":60,"l":0,"b":0},
                showlegend=False,
                title_font_size=16,
                uirevision=f'{commuting_threshold}_{migration_threshold}_{len(final_hmas)}'  # Unique key forces complete redraw
            )
            print("✓ Updated map layout")
            
            # Ensure figure is properly finalized
            print(f"Figure data length: {len(fig.data)}")
            print(f"Figure has {len(fig.data)} traces")
            
        except Exception as e:
            print(f"ERROR creating map: {str(e)}")
            import traceback
            traceback.print_exc()
            raise
        
        # Create stats output
        print("Creating statistics panel...")
        try:
            stats = html.Div([
                html.H3("Summary Statistics", 
                        style={'color': '#2c3e50', 'marginBottom': 25, 'fontSize': 22, 'fontWeight': '600'}),
                
                # Stats Grid
                html.Div([
                    # Stat Card 1
                    html.Div([
                        html.Div(f"{len(final_hmas)}", 
                                style={'fontSize': 36, 'fontWeight': '700', 'color': '#667eea', 'marginBottom': 5}),
                        html.Div("Total HMAs", 
                                style={'fontSize': 14, 'color': '#7f8c8d', 'fontWeight': '500'})
                    ], style={
                        'backgroundColor': '#f8f9fd',
                        'padding': 20,
                        'borderRadius': 10,
                        'textAlign': 'center',
                        'border': '2px solid #e8ebf7'
                    }),
                    
                    # Stat Card 2
                    html.Div([
                        html.Div(f"{combined_hma_df['HMA_Size'].mean():.1f}", 
                                style={'fontSize': 36, 'fontWeight': '700', 'color': '#667eea', 'marginBottom': 5}),
                        html.Div("Mean HMA Size (LAs)", 
                                style={'fontSize': 14, 'color': '#7f8c8d', 'fontWeight': '500'})
                    ], style={
                        'backgroundColor': '#f8f9fd',
                        'padding': 20,
                        'borderRadius': 10,
                        'textAlign': 'center',
                        'border': '2px solid #e8ebf7'
                    }),
                    
                    # Stat Card 3
                    html.Div([
                        html.Div(f"{combined_hma_df['HMA_Size'].max()}", 
                                style={'fontSize': 36, 'fontWeight': '700', 'color': '#667eea', 'marginBottom': 5}),
                        html.Div("Largest HMA (LAs)", 
                                style={'fontSize': 14, 'color': '#7f8c8d', 'fontWeight': '500'})
                    ], style={
                        'backgroundColor': '#f8f9fd',
                        'padding': 20,
                        'borderRadius': 10,
                        'textAlign': 'center',
                        'border': '2px solid #e8ebf7'
                    }),
                    
                    # Stat Card 4
                    html.Div([
                        html.Div(f"{combined_hma_df['HMA_Size'].median():.0f}", 
                                style={'fontSize': 36, 'fontWeight': '700', 'color': '#667eea', 'marginBottom': 5}),
                        html.Div("Median HMA Size", 
                                style={'fontSize': 14, 'color': '#7f8c8d', 'fontWeight': '500'})
                    ], style={
                        'backgroundColor': '#f8f9fd',
                        'padding': 20,
                        'borderRadius': 10,
                        'textAlign': 'center',
                        'border': '2px solid #e8ebf7'
                    }),
                ], style={
                    'display': 'grid',
                    'gridTemplateColumns': 'repeat(auto-fit, minmax(200px, 1fr))',
                    'gap': 20,
                    'marginBottom': 30
                }),
                
                # Detailed Stats
                html.Div([
                    html.H4("Algorithm Results", 
                           style={'color': '#34495e', 'marginBottom': 15, 'fontSize': 18, 'fontWeight': '600'}),
                    html.Div([
                        html.Div([
                            html.Span("Passed both tests initially: ", 
                                     style={'fontWeight': '600', 'color': '#27ae60'}),
                            html.Span(f"{len(passed_regions)} regions", 
                                     style={'color': '#2c3e50'})
                        ], style={'marginBottom': 10}),
                        html.Div([
                            html.Span("Re-grouped from failed areas: ", 
                                     style={'fontWeight': '600', 'color': '#f39c12'}),
                            html.Span(f"{len(migration_regions)} regions", 
                                     style={'color': '#2c3e50'})
                        ], style={'marginBottom': 10}),
                        html.Div([
                            html.Span("Mean commuting closure: ", 
                                     style={'fontWeight': '600', 'color': '#3498db'}),
                            html.Span(f"{combined_hma_df.groupby('HMA_ID')['Commuting_SC'].first().mean():.1%}", 
                                     style={'color': '#2c3e50'})
                        ], style={'marginBottom': 10}),
                        html.Div([
                            html.Span("Mean migration closure: ", 
                                     style={'fontWeight': '600', 'color': '#9b59b6'}),
                            html.Span(f"{combined_hma_df.groupby('HMA_ID')['Migration_SC'].first().mean():.1%}", 
                                     style={'color': '#2c3e50'})
                        ]),
                    ], style={
                        'backgroundColor': '#f8f9fd',
                        'padding': 20,
                        'borderRadius': 8,
                        'fontSize': 15
                    })
                ], style={'marginTop': 10})
            ])
            print("✓ Created statistics panel")
        except Exception as e:
            print(f"ERROR creating stats: {str(e)}")
            import traceback
            traceback.print_exc()
            stats = html.Div(f"Error creating statistics: {str(e)}")
        
        print(f"\n{'='*80}")
        print(f"ALGORITHM COMPLETE")
        print(f"Generated {len(final_hmas)} Housing Market Areas")
        print(f"{'='*80}\n")
        
        print("Preparing return values...")
        print(f"  fig type: {type(fig)}")
        print(f"  stats type: {type(stats)}")
        status_msg = f"Algorithm complete. Generated {len(final_hmas)} HMAs"
        print(f"  status_msg type: {type(status_msg)}")
        print("Returning from callback...")
        
        return fig, stats, status_msg
    
    except Exception as e:
        print(f"\n{'='*80}")
        print(f"FATAL ERROR IN CALLBACK:")
        print(f"{'='*80}")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        import traceback
        print("\nFull traceback:")
        traceback.print_exc()
        print(f"{'='*80}\n")
        
        # Return error message to user
        error_fig = px.choropleth_mapbox(
            mapbox_style='carto-positron',
            center={"lat": 52.5, "lon": -2},
            zoom=5.5
        )
        error_fig.update_layout(
            margin={"r":0,"t":60,"l":0,"b":0},
            title=f"Error: {str(e)}"
        )
        error_msg = html.Div([
            html.H3("Error Details:", style={'color': 'red'}),
            html.P(f"Type: {type(e).__name__}"),
            html.P(f"Message: {str(e)}"),
            html.P("Check terminal output for full traceback")
        ])
        return error_fig, error_msg, f"✗ Error: {str(e)}"

@app.callback(
    Output('download-dataframe-csv', 'data'),
    Input('download-button', 'n_clicks'),
    prevent_initial_call=True
)
def download_results(n_clicks):
    """Download the current HMA results as CSV"""
    global current_results
    
    if current_results is None:
        print("No results to download yet")
        return None
    
    # Merge with gdf to get LAD23NM
    download_df = current_results.merge(
        gdf_la_2023[['LAD23CD', 'LAD23NM']], 
        on='LAD23CD', 
        how='left'
    )
    
    # Select and order columns
    download_df = download_df[['LAD23CD', 'LAD23NM', 'HMA_ID', 'HMA_Size', 'Commuting_SC', 'Migration_SC']]
    
    # Sort by HMA_ID and LAD code
    download_df = download_df.sort_values(['HMA_ID', 'LAD23CD'])
    
    print(f"Preparing download: {len(download_df)} rows")
    
    return dcc.send_data_frame(download_df.to_csv, "housing_market_areas.csv", index=False)

if __name__ == '__main__':
    print("Starting dashboard on http://127.0.0.1:8051")
    app.run(debug=True, port=8051)
